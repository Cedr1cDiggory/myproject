#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Batch validator for CARLA-generated OpenLane/Anchor3DLane-style json frames.

Assumptions (matches the preprocessing you showed):
- lane_lines[].xyz is 3xN in OpenLane camera frame
- extrinsic is 4x4: Apollo camera -> Ground/Ego (cam_to_ground)
- intrinsic is 3x3 K
- Preprocess chain:
    p_apollo = T_open_to_apollo * p_open
    p_ground = E_apollo_cam_to_ground * p_apollo
  Projection used by preprocess:
    P = K * inv(E)[:3, :]
    uv = P * [Xg, Yg, Zg, 1]^T
"""

import argparse
import json
import math
import os
import random
import glob
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Tuple, Optional

import numpy as np


# -----------------------------
# Fixed transform from your preprocess
# Apollo camera -> OpenLane camera
# -----------------------------
def T_apollo_to_openlane() -> np.ndarray:
    T = np.eye(4, dtype=np.float64)
    T[0, :3] = [0, 0, 1]
    T[1, :3] = [-1, 0, 0]
    T[2, :3] = [0, -1, 0]
    return T


def safe_np(a, shape=None, name="array") -> np.ndarray:
    arr = np.array(a, dtype=np.float64)
    if shape is not None and tuple(arr.shape) != tuple(shape):
        raise ValueError(f"{name} shape mismatch: expected {shape}, got {arr.shape}")
    return arr


def parse_xyz(xyz_field) -> np.ndarray:
    """
    xyz in json is expected as 3 x N list-of-lists.
    Returns 3 x N float64.
    """
    xyz = np.array(xyz_field, dtype=np.float64)
    if xyz.ndim != 2:
        raise ValueError(f"xyz must be 2D, got ndim={xyz.ndim}")
    # accept both 3xN and Nx3
    if xyz.shape[0] == 3:
        return xyz
    if xyz.shape[1] == 3:
        return xyz.T
    raise ValueError(f"xyz must be 3xN or Nx3, got {xyz.shape}")


def parse_uv(uv_field) -> np.ndarray:
    """
    uv in json may be 2 x N or N x 2
    Returns 2 x N float64.
    """
    uv = np.array(uv_field, dtype=np.float64)
    if uv.ndim != 2:
        raise ValueError(f"uv must be 2D, got ndim={uv.ndim}")
    if uv.shape[0] == 2:
        return uv
    if uv.shape[1] == 2:
        return uv.T
    raise ValueError(f"uv must be 2xN or Nx2, got {uv.shape}")


def to_h(pts3xN: np.ndarray) -> np.ndarray:
    return np.vstack([pts3xN, np.ones((1, pts3xN.shape[1]), dtype=np.float64)])


def openlane_to_ground(xyz_open_3xN: np.ndarray, E_apollo_cam_to_ground: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns:
      pts_apollo_3xN, pts_ground_3xN
    """
    T_A2O = T_apollo_to_openlane()
    T_O2A = np.linalg.inv(T_A2O)

    pts_open_h = to_h(xyz_open_3xN)                 # 4xN
    pts_apollo = (T_O2A @ pts_open_h)[:3, :]        # 3xN
    pts_apollo_h = to_h(pts_apollo)
    pts_ground = (E_apollo_cam_to_ground @ pts_apollo_h)[:3, :]  # 3xN
    return pts_apollo, pts_ground


def project_ground_to_uv(pts_ground_3xN: np.ndarray, E_cam_to_ground: np.ndarray, K: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Exactly like projection_g2im_extrinsic(E,K):
      P = K * inv(E)[:3,:]  (ground -> cam)
      uv = P * [Xg,Yg,Zg,1]
    Returns:
      uv_2xN, depth_cam (z in cam)
    """
    P = K @ np.linalg.inv(E_cam_to_ground)[0:3, :]  # 3x4
    pts_h = to_h(pts_ground_3xN)
    proj = P @ pts_h  # 3xN
    z = proj[2, :]
    z_safe = np.where(z != 0, z, 1e-9)
    u = proj[0, :] / z_safe
    v = proj[1, :] / z_safe
    return np.vstack([u, v]), z


@dataclass
class FrameReport:
    path: str
    ok: bool
    reason: str

    n_lanes: int
    n_points_total: int
    n_vis_total: int

    reproj_mean_px: float
    reproj_p95_px: float
    reproj_max_px: float

    y_nonmono_ratio: float      # ratio of negative diffs in ground y
    x_range_min: float
    x_range_max: float
    y_range_min: float
    y_range_max: float
    z_mean: float
    z_abs_p95: float

    vis_uv_mismatch: float      # fraction of points where (vis==0) but uv not -1 (or vice versa)


def percentile(a: np.ndarray, q: float) -> float:
    if a.size == 0:
        return float("nan")
    return float(np.percentile(a, q))


def validate_frame(frame: Dict[str, Any],
                   path: str,
                   image_w: Optional[int],
                   image_h: Optional[int],
                   x_limit: float = 30.0,
                   y_max_expect: float = 200.0) -> FrameReport:
    """
    Validate one json frame.
    image_w/h optional: if provided, we also check uv inside bounds for vis points.
    """
    try:
        K = safe_np(frame["intrinsic"], shape=(3, 3), name="intrinsic")
        E = safe_np(frame["extrinsic"], shape=(4, 4), name="extrinsic")
        lanes = frame.get("lane_lines", [])
        if not isinstance(lanes, list):
            raise ValueError("lane_lines is not a list")

        all_reproj_err = []
        all_y_nonmono = []
        xs = []
        ys = []
        zs = []
        mismatch_flags = []

        n_points_total = 0
        n_vis_total = 0

        for lane in lanes:
            if "xyz" not in lane:
                continue
            xyz_open = parse_xyz(lane["xyz"])  # 3xN
            N = xyz_open.shape[1]
            if N < 2:
                continue

            vis = lane.get("visibility", [1] * N)
            vis = np.array(vis, dtype=np.float64).reshape(-1)
            if vis.size != N:
                # try to broadcast if it's wrong length
                vis = np.ones((N,), dtype=np.float64)

            uv = lane.get("uv", None)
            if uv is not None:
                uv = parse_uv(uv)  # 2xN
                if uv.shape[1] != N:
                    uv = None

            # Transform to ground
            _, pts_ground = openlane_to_ground(xyz_open, E)
            xg, yg, zg = pts_ground[0, :], pts_ground[1, :], pts_ground[2, :]

            xs.append(xg)
            ys.append(yg)
            zs.append(zg)

            # y monotonic check (ground y should roughly increase along lane)
            dy = np.diff(yg)
            if dy.size > 0:
                nonmono = np.mean(dy <= 0)
                all_y_nonmono.append(nonmono)

            # Reprojection check: use ground points -> uv
            if uv is not None:
                uv_pred, z_cam = project_ground_to_uv(pts_ground, E, K)
                # Only evaluate where vis==1 and uv is not -1,-1 (optional)
                mask = vis > 0.5
                if mask.any():
                    u_err = uv_pred[0, mask] - uv[0, mask]
                    v_err = uv_pred[1, mask] - uv[1, mask]
                    err = np.sqrt(u_err * u_err + v_err * v_err)
                    all_reproj_err.append(err)

                    # Optional bounds check if image size provided
                    if image_w is not None and image_h is not None:
                        inb = (uv_pred[0, mask] >= 0) & (uv_pred[0, mask] < image_w) & \
                              (uv_pred[1, mask] >= 0) & (uv_pred[1, mask] < image_h)
                        # not failing hard, but could be a warning
                        # (you can promote this to an error if you want)

                # vis/uv mismatch check:
                # convention: if vis==0 => uv should be (-1,-1) (or at least negative)
                uv_neg = (uv[0, :] < 0) & (uv[1, :] < 0)
                mismatch = np.mean((vis > 0.5) & uv_neg) + np.mean((vis <= 0.5) & (~uv_neg))
                # The above counts both mismatch types; scale to [0,1] approximately by /2
                mismatch_flags.append(float(mismatch) / 2.0)

            n_points_total += N
            n_vis_total += int(np.sum(vis > 0.5))

        if len(xs) == 0:
            return FrameReport(
                path=path, ok=False, reason="no_valid_lanes",
                n_lanes=len(lanes), n_points_total=0, n_vis_total=0,
                reproj_mean_px=float("nan"), reproj_p95_px=float("nan"), reproj_max_px=float("nan"),
                y_nonmono_ratio=float("nan"),
                x_range_min=float("nan"), x_range_max=float("nan"),
                y_range_min=float("nan"), y_range_max=float("nan"),
                z_mean=float("nan"), z_abs_p95=float("nan"),
                vis_uv_mismatch=float("nan")
            )

        X = np.concatenate(xs)
        Y = np.concatenate(ys)
        Z = np.concatenate(zs)

        # Aggregate reproj errors
        if len(all_reproj_err) > 0:
            E_all = np.concatenate(all_reproj_err)
            reproj_mean = float(np.mean(E_all)) if E_all.size else float("nan")
            reproj_p95 = percentile(E_all, 95)
            reproj_max = float(np.max(E_all)) if E_all.size else float("nan")
        else:
            reproj_mean = reproj_p95 = reproj_max = float("nan")

        # y non-mono
        y_nonmono_ratio = float(np.mean(all_y_nonmono)) if len(all_y_nonmono) else float("nan")

        # z stats
        z_mean = float(np.mean(Z))
        z_abs_p95 = percentile(np.abs(Z), 95)

        # vis/uv mismatch
        vis_uv_mismatch = float(np.mean(mismatch_flags)) if len(mismatch_flags) else float("nan")

        # Decide ok / reason
        ok = True
        reasons = []

        # These thresholds are conservative; tweak to your taste
        if not math.isnan(reproj_mean) and reproj_mean > 2.0:
            ok = False
            reasons.append(f"reproj_mean>2px({reproj_mean:.2f})")
        if not math.isnan(reproj_max) and reproj_max > 10.0:
            ok = False
            reasons.append(f"reproj_max>10px({reproj_max:.2f})")
        if not math.isnan(y_nonmono_ratio) and y_nonmono_ratio > 0.20:
            # allow some local noise, but too much indicates wrong axis or point order
            ok = False
            reasons.append(f"y_nonmono_ratio>0.20({y_nonmono_ratio:.2f})")
        if np.nanmax(np.abs(X)) > x_limit + 10:
            # if you intended lanes near vehicle only, large lateral could be wrong axis
            reasons.append(f"x_out_of_expected(|x|>{x_limit+10:.0f})")
        if np.nanmax(Y) < 10:
            reasons.append("y_too_short(<10m)")
        if vis_uv_mismatch is not None and (not math.isnan(vis_uv_mismatch)) and vis_uv_mismatch > 0.10:
            reasons.append(f"vis_uv_mismatch>0.10({vis_uv_mismatch:.2f})")

        reason = "ok" if ok else ";".join(reasons) if reasons else "failed_thresholds"

        return FrameReport(
            path=path, ok=ok, reason=reason,
            n_lanes=len(frame.get("lane_lines", [])),
            n_points_total=int(n_points_total),
            n_vis_total=int(n_vis_total),
            reproj_mean_px=float(reproj_mean),
            reproj_p95_px=float(reproj_p95),
            reproj_max_px=float(reproj_max),
            y_nonmono_ratio=float(y_nonmono_ratio),
            x_range_min=float(np.min(X)),
            x_range_max=float(np.max(X)),
            y_range_min=float(np.min(Y)),
            y_range_max=float(np.max(Y)),
            z_mean=float(z_mean),
            z_abs_p95=float(z_abs_p95),
            vis_uv_mismatch=float(vis_uv_mismatch),
        )

    except Exception as e:
        return FrameReport(
            path=path, ok=False, reason=f"exception:{type(e).__name__}:{e}",
            n_lanes=0, n_points_total=0, n_vis_total=0,
            reproj_mean_px=float("nan"), reproj_p95_px=float("nan"), reproj_max_px=float("nan"),
            y_nonmono_ratio=float("nan"),
            x_range_min=float("nan"), x_range_max=float("nan"),
            y_range_min=float("nan"), y_range_max=float("nan"),
            z_mean=float("nan"), z_abs_p95=float("nan"),
            vis_uv_mismatch=float("nan"),
        )


def load_frame(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read().strip()
    # support jsonl single line, or a json file
    if txt.startswith("{"):
        return json.loads(txt)
    # if it's jsonl, read first non-empty line
    for line in txt.splitlines():
        line = line.strip()
        if line:
            return json.loads(line)
    raise ValueError("Empty file")


def write_csv(reports: List[FrameReport], out_csv: str):
    import csv
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(reports[0]).keys()))
        w.writeheader()
        for r in reports:
            w.writerow(asdict(r))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True,
                    help="Directory of json frames, or a glob pattern like '/data/*.json'")
    ap.add_argument("-N", "--num_samples", type=int, default=500,
                    help="Randomly sample N frames (default 50). If N<=0 => use all.")
    ap.add_argument("--seed", type=int, default=0, help="Random seed")
    ap.add_argument("--w", type=int, default=None, help="Image width (optional, for uv bounds check)")
    ap.add_argument("--h", type=int, default=None, help="Image height (optional, for uv bounds check)")
    ap.add_argument("--out_csv", type=str, default="validation_report.csv", help="Output CSV path")
    args = ap.parse_args()

    # collect files
    if any(ch in args.input for ch in ["*", "?", "["]):
        files = sorted(glob.glob(args.input))
    else:
        # directory
        files = sorted(glob.glob(os.path.join(args.input, "*.json")))
        if not files:
            # maybe jsonl
            files = sorted(glob.glob(os.path.join(args.input, "*.jsonl")))
    if not files:
        raise SystemExit(f"No input files found for: {args.input}")

    # sample
    rng = random.Random(args.seed)
    if args.num_samples and args.num_samples > 0 and args.num_samples < len(files):
        files = rng.sample(files, args.num_samples)

    reports: List[FrameReport] = []
    for p in files:
        frame = load_frame(p)
        rep = validate_frame(frame, p, args.w, args.h)
        reports.append(rep)

    # summary
    ok_count = sum(1 for r in reports if r.ok)
    fail_count = len(reports) - ok_count

    reproj_means = np.array([r.reproj_mean_px for r in reports if not math.isnan(r.reproj_mean_px)], dtype=np.float64)
    nonmono = np.array([r.y_nonmono_ratio for r in reports if not math.isnan(r.y_nonmono_ratio)], dtype=np.float64)

    print("========== Batch Validation Summary ==========")
    print(f"Frames checked: {len(reports)}")
    print(f"OK: {ok_count}   FAIL: {fail_count}")
    if reproj_means.size:
        print(f"Reproj mean px: mean={reproj_means.mean():.4f}  p95={np.percentile(reproj_means,95):.4f}  max={reproj_means.max():.4f}")
    else:
        print("Reproj mean px: (no uv available)")
    if nonmono.size:
        print(f"Y non-mono ratio: mean={nonmono.mean():.4f}  p95={np.percentile(nonmono,95):.4f}  max={nonmono.max():.4f}")
    else:
        print("Y non-mono ratio: (no lanes)")

    # show top failing reasons
    from collections import Counter
    c = Counter([r.reason for r in reports if not r.ok])
    if c:
        print("\nTop failure reasons:")
        for k, v in c.most_common(8):
            print(f"  {v:>4}  {k}")

    # write csv
    write_csv(reports, args.out_csv)
    print(f"\nSaved per-frame report to: {args.out_csv}")


if __name__ == "__main__":
    main()
