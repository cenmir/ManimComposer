"""Involute spur gear geometry.

Creates points for 2D gear profiles, including root fillets, and a function for just the left flank involute curve.

"""

import numpy as np


def gear_radii(N, m, phi_deg=20):
    """Standard circle radii: pitch, base, tip, root."""
    phi = np.radians(phi_deg)
    pr = m * N / 2
    br = pr * np.cos(phi)
    tr = m * (N + 2) / 2
    rr = pr - 1.25 * m
    return pr, br, tr, rr


def unified_curve(t, base_r, t_tip_val):
    """Unified involute/radial curve. Returns (x, y) arrays."""
    v = t * t_tip_val
    v_pos = (v + np.sqrt(v**2)) / 2
    v_neg = (v - np.sqrt(v**2)) / 2
    x = base_r * (np.sin(v_pos) - v_pos * np.cos(v_pos))
    y = base_r * (np.cos(v_pos) + v_pos * np.sin(v_pos)) + v_neg * base_r
    return x, y


def gear_profile(N_teeth, module, phi_deg=20, n_pts=300):
    """Complete 2D gear profile as (x, y) arrays. No fillets."""
    pr, br, tr, rr = gear_radii(N_teeth, module, phi_deg)
    t_tip_val = np.sqrt((tr / br)**2 - 1)

    half_tooth_angle = np.pi / (2 * N_teeth)
    alpha_p = np.sqrt((pr / br)**2 - 1)
    inv_angle_at_pitch = np.arctan2(
        br * (np.sin(alpha_p) - alpha_p * np.cos(alpha_p)),
        br * (np.cos(alpha_p) + alpha_p * np.sin(alpha_p))
    )
    tooth_rotation = half_tooth_angle + inv_angle_at_pitch

    t_param = np.linspace(-1, 1, n_pts)
    xc, yc = unified_curve(t_param, br, t_tip_val)
    r_curve = np.sqrt(xc**2 + yc**2)
    mask = (r_curve >= rr - 0.01) & (r_curve <= tr + 0.01)
    xc, yc = xc[mask].copy(), yc[mask].copy()

    r0 = np.sqrt(xc[0]**2 + yc[0]**2)
    xc[0] *= rr / r0; yc[0] *= rr / r0
    rn = np.sqrt(xc[-1]**2 + yc[-1]**2)
    xc[-1] *= tr / rn; yc[-1] *= tr / rn

    all_x, all_y = [], []
    angular_pitch = 2 * np.pi / N_teeth

    for k in range(N_teeth):
        angle = k * angular_pitch

        cos_r, sin_r = np.cos(angle - tooth_rotation), np.sin(angle - tooth_rotation)
        rx = cos_r * (-xc) - sin_r * yc
        ry = sin_r * (-xc) + cos_r * yc
        all_x.append(rx)
        all_y.append(ry)

        cos_l, sin_l = np.cos(angle + tooth_rotation), np.sin(angle + tooth_rotation)
        lx = cos_l * xc - sin_l * yc
        ly = sin_l * xc + cos_l * yc

        theta_rt = np.arctan2(ry[-1], rx[-1])
        theta_lt = np.arctan2(ly[-1], lx[-1])
        d_tip = (theta_lt - theta_rt) % (2 * np.pi)
        tip_thetas = np.linspace(theta_rt, theta_rt + d_tip, 15)
        all_x.append(tr * np.cos(tip_thetas))
        all_y.append(tr * np.sin(tip_thetas))

        all_x.append(lx[::-1])
        all_y.append(ly[::-1])

        theta_lr = np.arctan2(ly[0], lx[0])
        ncos = np.cos(angle + angular_pitch - tooth_rotation)
        nsin = np.sin(angle + angular_pitch - tooth_rotation)
        theta_nr = np.arctan2(
            nsin * (-xc[0]) + ncos * yc[0],
            ncos * (-xc[0]) - nsin * yc[0]
        )
        d_root = (theta_nr - theta_lr) % (2 * np.pi)
        root_thetas = np.linspace(theta_lr, theta_lr + d_root, 15)
        all_x.append(rr * np.cos(root_thetas))
        all_y.append(rr * np.sin(root_thetas))

    return np.concatenate(all_x), np.concatenate(all_y)


def gear_profile_points(N_teeth=20, module=1, phi_deg=20, n_flank=200, n_fillet=15,
                        start_tooth=0):
    """Closed gear outline with root fillets. Returns Nx3 array for manim."""
    phi = np.radians(phi_deg)
    pr, br, tr, rr = gear_radii(N_teeth, module, phi_deg)
    t_tip_val = np.sqrt((tr / br)**2 - 1)

    inv_phi = np.tan(phi) - phi
    R_f = 0.9 * br * (np.pi / (2 * N_teeth) - inv_phi)
    r_ft = np.sqrt(rr**2 + 2 * rr * R_f)
    delta_f = np.arcsin(R_f / (rr + R_f))

    half_tooth = np.pi / (2 * N_teeth)
    alpha_p = np.sqrt((pr / br)**2 - 1)
    inv_at_pitch = np.arctan2(
        br * (np.sin(alpha_p) - alpha_p * np.cos(alpha_p)),
        br * (np.cos(alpha_p) + alpha_p * np.sin(alpha_p)),
    )
    tooth_rot = half_tooth + inv_at_pitch
    ang_pitch = 2 * np.pi / N_teeth

    t_param = np.linspace(-1, 1, n_flank)
    xc, yc = unified_curve(t_param, br, t_tip_val)
    rc = np.sqrt(xc**2 + yc**2)
    mask = (rc >= r_ft - 0.01) & (rc <= tr + 0.01)
    xc, yc = xc[mask].copy(), yc[mask].copy()
    r0 = np.hypot(xc[0], yc[0])
    xc[0] *= r_ft / r0; yc[0] *= r_ft / r0
    rn = np.hypot(xc[-1], yc[-1])
    xc[-1] *= tr / rn; yc[-1] *= tr / rn

    def fillet_arc(theta_flank, direction):
        theta_c = theta_flank + direction * delta_f
        cx = (rr + R_f) * np.cos(theta_c)
        cy = (rr + R_f) * np.sin(theta_c)
        a_root = np.arctan2(rr * np.sin(theta_c) - cy, rr * np.cos(theta_c) - cx)
        a_flank = np.arctan2(r_ft * np.sin(theta_flank) - cy,
                             r_ft * np.cos(theta_flank) - cx)
        if direction < 0:
            d = (a_flank - a_root) % (2 * np.pi)
            if d > np.pi: d -= 2 * np.pi
            thetas = np.linspace(a_root, a_root + d, n_fillet)
        else:
            d = (a_root - a_flank) % (2 * np.pi)
            if d > np.pi: d -= 2 * np.pi
            thetas = np.linspace(a_flank, a_flank + d, n_fillet)
        return cx + R_f * np.cos(thetas), cy + R_f * np.sin(thetas)

    all_x, all_y = [], []
    for i in range(N_teeth):
        k = (i + start_tooth) % N_teeth
        angle = k * ang_pitch
        cr, sr = np.cos(angle - tooth_rot), np.sin(angle - tooth_rot)
        rx = cr * (-xc) - sr * yc
        ry = sr * (-xc) + cr * yc
        cl, sl = np.cos(angle + tooth_rot), np.sin(angle + tooth_rot)
        lx = cl * xc - sl * yc
        ly = sl * xc + cl * yc

        theta_rf = np.arctan2(ry[0], rx[0])
        theta_lf = np.arctan2(ly[0], lx[0])

        fx, fy = fillet_arc(theta_rf, -1)
        all_x.append(fx); all_y.append(fy)
        all_x.append(rx); all_y.append(ry)

        th_rt = np.arctan2(ry[-1], rx[-1])
        th_lt = np.arctan2(ly[-1], lx[-1])
        d_tip = (th_lt - th_rt) % (2 * np.pi)
        tip_th = np.linspace(th_rt, th_rt + d_tip, 15)
        all_x.append(tr * np.cos(tip_th)); all_y.append(tr * np.sin(tip_th))

        all_x.append(lx[::-1]); all_y.append(ly[::-1])

        fx, fy = fillet_arc(theta_lf, +1)
        all_x.append(fx); all_y.append(fy)

        th_start = theta_lf + delta_f
        k_next = (k + 1) % N_teeth
        angle_next = k_next * ang_pitch
        nc, ns = np.cos(angle_next - tooth_rot), np.sin(angle_next - tooth_rot)
        nrx = nc * (-xc[0]) - ns * yc[0]
        nry = ns * (-xc[0]) + nc * yc[0]
        th_end = np.arctan2(nry, nrx) - delta_f
        d_root = (th_end - th_start) % (2 * np.pi)
        root_th = np.linspace(th_start, th_start + d_root, 15)
        all_x.append(rr * np.cos(root_th)); all_y.append(rr * np.sin(root_th))

    gx = np.concatenate(all_x)
    gy = np.concatenate(all_y)
    return np.column_stack([gx, gy, np.zeros_like(gx)])


def involute_left_flank(N_teeth, module, phi_deg=20, n_pts=100, overshoot = 1.0):
    """Returns the left flank involute curve starting from the base circle."""
    pr, br, tr, rr = gear_radii(N_teeth, module, phi_deg)
    t_tip_val = np.sqrt((tr / br)**2 - 1)

    # Parameter t from 0 to 1 corresponds to involute from base circle to tip
    t_param = np.linspace(0, 1*overshoot, n_pts)
    xc, yc = unified_curve(t_param, br, t_tip_val)

    half_tooth_angle = np.pi / (2 * N_teeth)
    alpha_p = np.sqrt((pr / br)**2 - 1)
    inv_angle_at_pitch = np.arctan2(
        br * (np.sin(alpha_p) - alpha_p * np.cos(alpha_p)),
        br * (np.cos(alpha_p) + alpha_p * np.sin(alpha_p))
    )
    tooth_rotation = half_tooth_angle + inv_angle_at_pitch

    # Left flank rotation for the first tooth (k=0)
    cos_l, sin_l = np.cos(tooth_rotation), np.sin(tooth_rotation)
    lx = cos_l * xc - sin_l * yc
    ly = sin_l * xc + cos_l * yc
    
    return np.column_stack([lx, ly, np.zeros_like(lx)])
