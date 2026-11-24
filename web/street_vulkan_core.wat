;; ============================================================================
;; StreetVulkan Core - Pure WebAssembly Text (.wat) Math & Simulation Kernel
;; ============================================================================
;; Direct translation of:
;;   - include/math_camera.h  (camera_get_vectors, mat4_multiply, mat4_lookat,
;;                             mat4_perspective_webgpu / mat4_perspective_webgl)
;;   - include/frustum_cull.h (frustum_extract, cull_chunks / frustum_test_aabb)
;;   - src/traffic_system.c   (traffic_tick deterministic 24s 4-phase cycle)
;;
;; Exported Linear Memory:
;;   "memory" -> 2 pages = 131,072 bytes (128 KiB), zero internal static scratch.
;;   All functions operate purely via WASM locals and caller-provided pointers,
;;   so the host JS/WebGPU client can partition the 2-page memory freely.
;;
;; Recommended Caller Memory Layout (all 4-byte aligned unless noted):
;;   0x0000 .. 0x0003 ( 4 B): reserved NULL guard (C/Emscripten ABI parity)
;;   0x0004 .. 0x000F (12 B): camera position [x, y, z] (3 x f32)
;;   0x0010 .. 0x0013 ( 4 B): traffic simulation time (1 x f32)
;;   0x0014 .. 0x0037 (36 B): optional camera_get_vectors out [fwd(12), right(12), up(12)]
;;   0x0040 .. 0x007F (64 B): view matrix (16 x f32, column-major)
;;   0x0080 .. 0x00BF (64 B): proj matrix (16 x f32, column-major)
;;   0x00C0 .. 0x00FF (64 B): mvp matrix  (16 x f32, column-major)
;;   0x0100 .. 0x015F (96 B): 6 frustum planes (6 x vec4 f32: a,b,c,d)
;;   0x0200 .. ...          : chunk AABBs (N x 24 B: minx,miny,minz,maxx,maxy,maxz)
;;   0x8000 .. ...          : chunk visibility flags (N x 1 B: 0=culled, 1=visible)
;; ============================================================================

(module
  ;; 2-page (128 KiB) exported linear memory
  (memory (export "memory") 2)

  ;; --------------------------------------------------------------------------
  ;; Internal High-Precision Trigonometry Helpers (f64 Cody-Waite + Taylor)
  ;; --------------------------------------------------------------------------
  ;; WASM has no native sin/cos/tan opcodes. We promote f32 -> f64, perform
  ;; Cody-Waite range reduction to [-pi/4, +pi/4], evaluate degree-11/12 Taylor
  ;; polynomials in f64 (omitted error < 1e-11), and demote back to f32 (<1 ULP).

  (func $trig_f64 (param $x f64) (param $is_cos i32) (result f64)
    (local $ax f64)
    (local $kf f64)
    (local $k i32)
    (local $q i32)
    (local $r f64)
    (local $r2 f64)
    (local $poly f64)

    ;; Handle NaN / Inf safely without trapping i32.trunc_f64_s
    (if (f64.ne (local.get $x) (local.get $x))
      (then (return (local.get $x)))
    )
    (local.set $ax (f64.abs (local.get $x)))
    (if (f64.ge (local.get $ax) (f64.const 1000000.0))
      (then
        ;; Large argument coarse reduction modulo 2*pi
        (local.set $x
          (f64.sub
            (local.get $x)
            (f64.mul
              (f64.nearest (f64.mul (local.get $x) (f64.const 0.15915494309189533577)))
              (f64.const 6.28318530717958647692)
            )
          )
        )
        (if (f64.ne (local.get $x) (local.get $x))
          (then (return (local.get $x)))
        )
      )
    )

    ;; Quadrant index k = nearest(x * 2 / pi)
    (local.set $kf (f64.nearest (f64.mul (local.get $x) (f64.const 0.63661977236758134308))))
    (local.set $k (i32.trunc_f64_s (local.get $kf)))

    ;; Cody-Waite reduction: r = (x - k * PIO2_HI) - k * PIO2_LO
    (local.set $r
      (f64.sub
        (f64.sub
          (local.get $x)
          (f64.mul (local.get $kf) (f64.const 0x1.921fb54442d18p+0))
        )
        (f64.mul (local.get $kf) (f64.const 0x1.1a62633145c07p-53))
      )
    )
    (local.set $r2 (f64.mul (local.get $r) (local.get $r)))

    ;; Quadrant shift for cos(x) = sin(x + pi/2)
    (local.set $q (i32.and (i32.add (local.get $k) (local.get $is_cos)) (i32.const 3)))

    ;; Even quadrants (0, 2) evaluate sin(r); odd quadrants (1, 3) evaluate cos(r)
    (if (result f64) (i32.eqz (i32.and (local.get $q) (i32.const 1)))
      (then
        ;; sin(r) = r * (1 + r^2 * (-1/6 + r^2 * (1/120 + r^2 * (-1/5040 + r^2 * (1/362880 - r^2/39916800)))))
        (local.set $poly
          (f64.add (f64.const 2.7557319223985893e-6)
            (f64.mul (local.get $r2) (f64.const -2.505210838544172e-8))
          )
        )
        (local.set $poly (f64.add (f64.const -1.9841269841269841e-4) (f64.mul (local.get $r2) (local.get $poly))))
        (local.set $poly (f64.add (f64.const 8.333333333333333e-3) (f64.mul (local.get $r2) (local.get $poly))))
        (local.set $poly (f64.add (f64.const -1.6666666666666666e-1) (f64.mul (local.get $r2) (local.get $poly))))
        (local.set $poly (f64.mul (local.get $r) (f64.add (f64.const 1.0) (f64.mul (local.get $r2) (local.get $poly)))))
        (local.get $poly)
      )
      (else
        ;; cos(r) = 1 + r^2 * (-1/2 + r^2 * (1/24 + r^2 * (-1/720 + r^2 * (1/40320 + r^2 * (-1/3628800 + r^2/479001600)))))
        (local.set $poly
          (f64.add (f64.const -2.755731922398589e-7)
            (f64.mul (local.get $r2) (f64.const 2.08767569878681e-9))
          )
        )
        (local.set $poly (f64.add (f64.const 2.48015873015873e-5) (f64.mul (local.get $r2) (local.get $poly))))
        (local.set $poly (f64.add (f64.const -1.388888888888889e-3) (f64.mul (local.get $r2) (local.get $poly))))
        (local.set $poly (f64.add (f64.const 4.1666666666666664e-2) (f64.mul (local.get $r2) (local.get $poly))))
        (local.set $poly (f64.add (f64.const -0.5) (f64.mul (local.get $r2) (local.get $poly))))
        (local.set $poly (f64.add (f64.const 1.0) (f64.mul (local.get $r2) (local.get $poly))))
        (local.get $poly)
      )
    )
    (local.set $poly)

    ;; Negate for quadrants 2 and 3
    (if (result f64) (i32.and (local.get $q) (i32.const 2))
      (then (f64.neg (local.get $poly)))
      (else (local.get $poly))
    )
  )

  (func $sin_f32 (param $x f32) (result f32)
    (f32.demote_f64 (call $trig_f64 (f64.promote_f32 (local.get $x)) (i32.const 0)))
  )

  (func $cos_f32 (param $x f32) (result f32)
    (f32.demote_f64 (call $trig_f64 (f64.promote_f32 (local.get $x)) (i32.const 1)))
  )

  (func $tan_f32 (param $x f32) (result f32)
    (local $xd f64)
    (local.set $xd (f64.promote_f32 (local.get $x)))
    (f32.demote_f64
      (f64.div
        (call $trig_f64 (local.get $xd) (i32.const 0))
        (call $trig_f64 (local.get $xd) (i32.const 1))
      )
    )
  )

  ;; --------------------------------------------------------------------------
  ;; 1. get_version() -> i32
  ;; --------------------------------------------------------------------------
  (func (export "get_version") (result i32)
    (i32.const 1)
  )

  ;; --------------------------------------------------------------------------
  ;; 2. camera_get_vectors(yaw_deg, pitch_deg, out_fwd_ptr, out_right_ptr, out_up_ptr)
  ;;    Matches include/math_camera.h:camera_get_vectors exact formulas.
  ;;    Pass -1 to skip writing any optional output pointer.
  ;; --------------------------------------------------------------------------
  (func $camera_get_vectors
    (export "camera_get_vectors")
    (param $yaw_deg f32)
    (param $pitch_deg f32)
    (param $fwd_ptr i32)
    (param $right_ptr i32)
    (param $up_ptr i32)
    (local $yaw_rad f32)
    (local $pitch_rad f32)
    (local $cy f32)
    (local $sy f32)
    (local $cp f32)
    (local $sp f32)
    (local $fx f32)
    (local $fy f32)
    (local $fz f32)
    (local $flen f32)
    (local $rx f32)
    (local $rz f32)
    (local $rlen f32)
    (local $ux f32)
    (local $uy f32)
    (local $uz f32)
    (local $ulen f32)

    ;; DEG2RAD(d) = d * 0.017453292519943295f
    (local.set $yaw_rad (f32.mul (local.get $yaw_deg) (f32.const 0.017453292519943295)))
    (local.set $pitch_rad (f32.mul (local.get $pitch_deg) (f32.const 0.017453292519943295)))

    (local.set $cy (call $cos_f32 (local.get $yaw_rad)))
    (local.set $sy (call $sin_f32 (local.get $yaw_rad)))
    (local.set $cp (call $cos_f32 (local.get $pitch_rad)))
    (local.set $sp (call $sin_f32 (local.get $pitch_rad)))

    ;; Forward = normalize(cos(pitch)*cos(yaw), sin(pitch), cos(pitch)*sin(yaw))
    (local.set $fx (f32.mul (local.get $cp) (local.get $cy)))
    (local.set $fy (local.get $sp))
    (local.set $fz (f32.mul (local.get $cp) (local.get $sy)))
    (local.set $flen
      (f32.sqrt
        (f32.add
          (f32.add (f32.mul (local.get $fx) (local.get $fx)) (f32.mul (local.get $fy) (local.get $fy)))
          (f32.mul (local.get $fz) (local.get $fz))
        )
      )
    )
    (if (f32.gt (local.get $flen) (f32.const 0.0))
      (then
        (local.set $fx (f32.div (local.get $fx) (local.get $flen)))
        (local.set $fy (f32.div (local.get $fy) (local.get $flen)))
        (local.set $fz (f32.div (local.get $fz) (local.get $flen)))
      )
    )

    ;; Right = normalize(-sin(yaw), 0, cos(yaw))
    (local.set $rx (f32.neg (local.get $sy)))
    (local.set $rz (local.get $cy))
    (local.set $rlen
      (f32.sqrt
        (f32.add (f32.mul (local.get $rx) (local.get $rx)) (f32.mul (local.get $rz) (local.get $rz)))
      )
    )
    (if (f32.gt (local.get $rlen) (f32.const 0.0))
      (then
        (local.set $rx (f32.div (local.get $rx) (local.get $rlen)))
        (local.set $rz (f32.div (local.get $rz) (local.get $rlen)))
      )
    )

    ;; Up = normalize(cross(right, forward)), with ry = 0
    (local.set $ux (f32.neg (f32.mul (local.get $rz) (local.get $fy))))
    (local.set $uy (f32.sub (f32.mul (local.get $rz) (local.get $fx)) (f32.mul (local.get $rx) (local.get $fz))))
    (local.set $uz (f32.mul (local.get $rx) (local.get $fy)))
    (local.set $ulen
      (f32.sqrt
        (f32.add
          (f32.add (f32.mul (local.get $ux) (local.get $ux)) (f32.mul (local.get $uy) (local.get $uy)))
          (f32.mul (local.get $uz) (local.get $uz))
        )
      )
    )
    (if (f32.gt (local.get $ulen) (f32.const 0.0))
      (then
        (local.set $ux (f32.div (local.get $ux) (local.get $ulen)))
        (local.set $uy (f32.div (local.get $uy) (local.get $ulen)))
        (local.set $uz (f32.div (local.get $uz) (local.get $ulen)))
      )
    )

    (if (i32.ge_s (local.get $fwd_ptr) (i32.const 0))
      (then
        (f32.store offset=0 (local.get $fwd_ptr) (local.get $fx))
        (f32.store offset=4 (local.get $fwd_ptr) (local.get $fy))
        (f32.store offset=8 (local.get $fwd_ptr) (local.get $fz))
      )
    )
    (if (i32.ge_s (local.get $right_ptr) (i32.const 0))
      (then
        (f32.store offset=0 (local.get $right_ptr) (local.get $rx))
        (f32.store offset=4 (local.get $right_ptr) (f32.const 0.0))
        (f32.store offset=8 (local.get $right_ptr) (local.get $rz))
      )
    )
    (if (i32.ge_s (local.get $up_ptr) (i32.const 0))
      (then
        (f32.store offset=0 (local.get $up_ptr) (local.get $ux))
        (f32.store offset=4 (local.get $up_ptr) (local.get $uy))
        (f32.store offset=8 (local.get $up_ptr) (local.get $uz))
      )
    )
  )

  ;; --------------------------------------------------------------------------
  ;; 3. camera_step(pos_ptr, yaw_deg, pitch_deg, move_fwd, move_right, move_up, speed, dt)
  ;;    Updates vec3 at pos_ptr ([0, 4, 8] bytes) along forward/right/up vectors.
  ;; --------------------------------------------------------------------------
  (func (export "camera_step")
    (param $pos_ptr i32)
    (param $yaw_deg f32)
    (param $pitch_deg f32)
    (param $move_fwd f32)
    (param $move_right f32)
    (param $move_up f32)
    (param $speed f32)
    (param $dt f32)
    (local $yaw_rad f32)
    (local $pitch_rad f32)
    (local $cy f32)
    (local $sy f32)
    (local $cp f32)
    (local $sp f32)
    (local $fx f32)
    (local $fy f32)
    (local $fz f32)
    (local $flen f32)
    (local $rx f32)
    (local $rz f32)
    (local $rlen f32)
    (local $ux f32)
    (local $uy f32)
    (local $uz f32)
    (local $ulen f32)
    (local $step f32)
    (local $px f32)
    (local $py f32)
    (local $pz f32)

    (local.set $yaw_rad (f32.mul (local.get $yaw_deg) (f32.const 0.017453292519943295)))
    (local.set $pitch_rad (f32.mul (local.get $pitch_deg) (f32.const 0.017453292519943295)))

    (local.set $cy (call $cos_f32 (local.get $yaw_rad)))
    (local.set $sy (call $sin_f32 (local.get $yaw_rad)))
    (local.set $cp (call $cos_f32 (local.get $pitch_rad)))
    (local.set $sp (call $sin_f32 (local.get $pitch_rad)))

    ;; Forward
    (local.set $fx (f32.mul (local.get $cp) (local.get $cy)))
    (local.set $fy (local.get $sp))
    (local.set $fz (f32.mul (local.get $cp) (local.get $sy)))
    (local.set $flen
      (f32.sqrt
        (f32.add
          (f32.add (f32.mul (local.get $fx) (local.get $fx)) (f32.mul (local.get $fy) (local.get $fy)))
          (f32.mul (local.get $fz) (local.get $fz))
        )
      )
    )
    (if (f32.gt (local.get $flen) (f32.const 0.0))
      (then
        (local.set $fx (f32.div (local.get $fx) (local.get $flen)))
        (local.set $fy (f32.div (local.get $fy) (local.get $flen)))
        (local.set $fz (f32.div (local.get $fz) (local.get $flen)))
      )
    )

    ;; Right (ry = 0)
    (local.set $rx (f32.neg (local.get $sy)))
    (local.set $rz (local.get $cy))
    (local.set $rlen
      (f32.sqrt
        (f32.add (f32.mul (local.get $rx) (local.get $rx)) (f32.mul (local.get $rz) (local.get $rz)))
      )
    )
    (if (f32.gt (local.get $rlen) (f32.const 0.0))
      (then
        (local.set $rx (f32.div (local.get $rx) (local.get $rlen)))
        (local.set $rz (f32.div (local.get $rz) (local.get $rlen)))
      )
    )

    ;; Up = normalize(cross(right, forward))
    (local.set $ux (f32.neg (f32.mul (local.get $rz) (local.get $fy))))
    (local.set $uy (f32.sub (f32.mul (local.get $rz) (local.get $fx)) (f32.mul (local.get $rx) (local.get $fz))))
    (local.set $uz (f32.mul (local.get $rx) (local.get $fy)))
    (local.set $ulen
      (f32.sqrt
        (f32.add
          (f32.add (f32.mul (local.get $ux) (local.get $ux)) (f32.mul (local.get $uy) (local.get $uy)))
          (f32.mul (local.get $uz) (local.get $uz))
        )
      )
    )
    (if (f32.gt (local.get $ulen) (f32.const 0.0))
      (then
        (local.set $ux (f32.div (local.get $ux) (local.get $ulen)))
        (local.set $uy (f32.div (local.get $uy) (local.get $ulen)))
        (local.set $uz (f32.div (local.get $uz) (local.get $ulen)))
      )
    )

    (local.set $step (f32.mul (local.get $speed) (local.get $dt)))
    (local.set $px (f32.load offset=0 (local.get $pos_ptr)))
    (local.set $py (f32.load offset=4 (local.get $pos_ptr)))
    (local.set $pz (f32.load offset=8 (local.get $pos_ptr)))

    ;; x += (move_fwd * fx + move_right * rx + move_up * ux) * step
    (local.set $px
      (f32.add (local.get $px)
        (f32.mul (local.get $step)
          (f32.add
            (f32.add (f32.mul (local.get $move_fwd) (local.get $fx)) (f32.mul (local.get $move_right) (local.get $rx)))
            (f32.mul (local.get $move_up) (local.get $ux))
          )
        )
      )
    )
    ;; y += (move_fwd * fy + move_up * uy) * step  (ry is 0)
    (local.set $py
      (f32.add (local.get $py)
        (f32.mul (local.get $step)
          (f32.add (f32.mul (local.get $move_fwd) (local.get $fy)) (f32.mul (local.get $move_up) (local.get $uy)))
        )
      )
    )
    ;; z += (move_fwd * fz + move_right * rz + move_up * uz) * step
    (local.set $pz
      (f32.add (local.get $pz)
        (f32.mul (local.get $step)
          (f32.add
            (f32.add (f32.mul (local.get $move_fwd) (local.get $fz)) (f32.mul (local.get $move_right) (local.get $rz)))
            (f32.mul (local.get $move_up) (local.get $uz))
          )
        )
      )
    )

    (f32.store offset=0 (local.get $pos_ptr) (local.get $px))
    (f32.store offset=4 (local.get $pos_ptr) (local.get $py))
    (f32.store offset=8 (local.get $pos_ptr) (local.get $pz))
  )

  ;; --------------------------------------------------------------------------
  ;; 4. mat4_perspective_webgpu(out_ptr, fovy_rad, aspect, znear, zfar)
  ;;    Right-handed perspective projection, WebGPU NDC (+Y up, Z in [0, 1]).
  ;;    Column-major 16 x f32 (64 bytes) at out_ptr.
  ;; --------------------------------------------------------------------------
  (func (export "mat4_perspective_webgpu")
    (param $out_ptr i32)
    (param $fovy_rad f32)
    (param $aspect f32)
    (param $znear f32)
    (param $zfar f32)
    (local $f f32)
    (local $inv_nf f32)

    (local.set $f (f32.div (f32.const 1.0) (call $tan_f32 (f32.mul (local.get $fovy_rad) (f32.const 0.5)))))
    (local.set $inv_nf (f32.div (f32.const 1.0) (f32.sub (local.get $znear) (local.get $zfar))))

    ;; Column 0
    (f32.store offset=0  (local.get $out_ptr) (f32.div (local.get $f) (local.get $aspect)))
    (f32.store offset=4  (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=8  (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=12 (local.get $out_ptr) (f32.const 0.0))

    ;; Column 1 (+f for WebGPU +Y-up NDC)
    (f32.store offset=16 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=20 (local.get $out_ptr) (local.get $f))
    (f32.store offset=24 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=28 (local.get $out_ptr) (f32.const 0.0))

    ;; Column 2 (Z in [0, 1])
    (f32.store offset=32 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=36 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=40 (local.get $out_ptr) (f32.mul (local.get $zfar) (local.get $inv_nf)))
    (f32.store offset=44 (local.get $out_ptr) (f32.const -1.0))

    ;; Column 3
    (f32.store offset=48 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=52 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=56 (local.get $out_ptr) (f32.mul (f32.mul (local.get $zfar) (local.get $znear)) (local.get $inv_nf)))
    (f32.store offset=60 (local.get $out_ptr) (f32.const 0.0))
  )

  ;; --------------------------------------------------------------------------
  ;; 5. mat4_perspective_webgl(out_ptr, fovy_rad, aspect, znear, zfar)
  ;;    Right-handed perspective projection, WebGL NDC (+Y up, Z in [-1, 1]).
  ;;    Column-major 16 x f32 (64 bytes) at out_ptr.
  ;; --------------------------------------------------------------------------
  (func (export "mat4_perspective_webgl")
    (param $out_ptr i32)
    (param $fovy_rad f32)
    (param $aspect f32)
    (param $znear f32)
    (param $zfar f32)
    (local $f f32)
    (local $inv_nf f32)

    (local.set $f (f32.div (f32.const 1.0) (call $tan_f32 (f32.mul (local.get $fovy_rad) (f32.const 0.5)))))
    (local.set $inv_nf (f32.div (f32.const 1.0) (f32.sub (local.get $znear) (local.get $zfar))))

    ;; Column 0
    (f32.store offset=0  (local.get $out_ptr) (f32.div (local.get $f) (local.get $aspect)))
    (f32.store offset=4  (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=8  (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=12 (local.get $out_ptr) (f32.const 0.0))

    ;; Column 1
    (f32.store offset=16 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=20 (local.get $out_ptr) (local.get $f))
    (f32.store offset=24 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=28 (local.get $out_ptr) (f32.const 0.0))

    ;; Column 2 (Z in [-1, 1])
    (f32.store offset=32 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=36 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=40 (local.get $out_ptr) (f32.mul (f32.add (local.get $zfar) (local.get $znear)) (local.get $inv_nf)))
    (f32.store offset=44 (local.get $out_ptr) (f32.const -1.0))

    ;; Column 3
    (f32.store offset=48 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=52 (local.get $out_ptr) (f32.const 0.0))
    (f32.store offset=56 (local.get $out_ptr)
      (f32.mul (f32.mul (f32.const 2.0) (f32.mul (local.get $zfar) (local.get $znear))) (local.get $inv_nf))
    )
    (f32.store offset=60 (local.get $out_ptr) (f32.const 0.0))
  )

  ;; --------------------------------------------------------------------------
  ;; 6. mat4_lookat(out_ptr, ex, ey, ez, cx, cy, cz, ux, uy, uz)
  ;;    Matches include/math_camera.h:mat4_lookat exact formula (column-major).
  ;; --------------------------------------------------------------------------
  (func (export "mat4_lookat")
    (param $out_ptr i32)
    (param $ex f32) (param $ey f32) (param $ez f32)
    (param $cx f32) (param $cy f32) (param $cz f32)
    (param $upx f32) (param $upy f32) (param $upz f32)
    (local $fx f32) (local $fy f32) (local $fz f32) (local $flen f32)
    (local $sx f32) (local $sy f32) (local $sz f32) (local $slen f32)
    (local $ux f32) (local $uy f32) (local $uz f32)

    ;; f = normalize(c - e)
    (local.set $fx (f32.sub (local.get $cx) (local.get $ex)))
    (local.set $fy (f32.sub (local.get $cy) (local.get $ey)))
    (local.set $fz (f32.sub (local.get $cz) (local.get $ez)))
    (local.set $flen
      (f32.sqrt
        (f32.add
          (f32.add (f32.mul (local.get $fx) (local.get $fx)) (f32.mul (local.get $fy) (local.get $fy)))
          (f32.mul (local.get $fz) (local.get $fz))
        )
      )
    )
    (if (f32.gt (local.get $flen) (f32.const 0.0))
      (then
        (local.set $fx (f32.div (local.get $fx) (local.get $flen)))
        (local.set $fy (f32.div (local.get $fy) (local.get $flen)))
        (local.set $fz (f32.div (local.get $fz) (local.get $flen)))
      )
    )

    ;; s = normalize(cross(f, up))
    (local.set $sx (f32.sub (f32.mul (local.get $fy) (local.get $upz)) (f32.mul (local.get $fz) (local.get $upy))))
    (local.set $sy (f32.sub (f32.mul (local.get $fz) (local.get $upx)) (f32.mul (local.get $fx) (local.get $upz))))
    (local.set $sz (f32.sub (f32.mul (local.get $fx) (local.get $upy)) (f32.mul (local.get $fy) (local.get $upx))))
    (local.set $slen
      (f32.sqrt
        (f32.add
          (f32.add (f32.mul (local.get $sx) (local.get $sx)) (f32.mul (local.get $sy) (local.get $sy)))
          (f32.mul (local.get $sz) (local.get $sz))
        )
      )
    )
    (if (f32.gt (local.get $slen) (f32.const 0.0))
      (then
        (local.set $sx (f32.div (local.get $sx) (local.get $slen)))
        (local.set $sy (f32.div (local.get $sy) (local.get $slen)))
        (local.set $sz (f32.div (local.get $sz) (local.get $slen)))
      )
    )

    ;; u = cross(s, f)
    (local.set $ux (f32.sub (f32.mul (local.get $sy) (local.get $fz)) (f32.mul (local.get $sz) (local.get $fy))))
    (local.set $uy (f32.sub (f32.mul (local.get $sz) (local.get $fx)) (f32.mul (local.get $sx) (local.get $fz))))
    (local.set $uz (f32.sub (f32.mul (local.get $sx) (local.get $fy)) (f32.mul (local.get $sy) (local.get $fx))))

    ;; Column 0
    (f32.store offset=0  (local.get $out_ptr) (local.get $sx))
    (f32.store offset=4  (local.get $out_ptr) (local.get $ux))
    (f32.store offset=8  (local.get $out_ptr) (f32.neg (local.get $fx)))
    (f32.store offset=12 (local.get $out_ptr) (f32.const 0.0))

    ;; Column 1
    (f32.store offset=16 (local.get $out_ptr) (local.get $sy))
    (f32.store offset=20 (local.get $out_ptr) (local.get $uy))
    (f32.store offset=24 (local.get $out_ptr) (f32.neg (local.get $fy)))
    (f32.store offset=28 (local.get $out_ptr) (f32.const 0.0))

    ;; Column 2
    (f32.store offset=32 (local.get $out_ptr) (local.get $sz))
    (f32.store offset=36 (local.get $out_ptr) (local.get $uz))
    (f32.store offset=40 (local.get $out_ptr) (f32.neg (local.get $fz)))
    (f32.store offset=44 (local.get $out_ptr) (f32.const 0.0))

    ;; Column 3
    (f32.store offset=48 (local.get $out_ptr)
      (f32.neg
        (f32.add
          (f32.add (f32.mul (local.get $sx) (local.get $ex)) (f32.mul (local.get $sy) (local.get $ey)))
          (f32.mul (local.get $sz) (local.get $ez))
        )
      )
    )
    (f32.store offset=52 (local.get $out_ptr)
      (f32.neg
        (f32.add
          (f32.add (f32.mul (local.get $ux) (local.get $ex)) (f32.mul (local.get $uy) (local.get $ey)))
          (f32.mul (local.get $uz) (local.get $ez))
        )
      )
    )
    (f32.store offset=56 (local.get $out_ptr)
      (f32.add
        (f32.add (f32.mul (local.get $fx) (local.get $ex)) (f32.mul (local.get $fy) (local.get $ey)))
        (f32.mul (local.get $fz) (local.get $ez))
      )
    )
    (f32.store offset=60 (local.get $out_ptr) (f32.const 1.0))
  )

  ;; --------------------------------------------------------------------------
  ;; 7. mat4_multiply(out_ptr, a_ptr, b_ptr)
  ;;    Computes out = a * b (column-major). Aliasing-safe via WASM locals.
  ;; --------------------------------------------------------------------------
  (func (export "mat4_multiply")
    (param $out_ptr i32) (param $a_ptr i32) (param $b_ptr i32)
    (local $a00 f32) (local $a10 f32) (local $a20 f32) (local $a30 f32)
    (local $a01 f32) (local $a11 f32) (local $a21 f32) (local $a31 f32)
    (local $a02 f32) (local $a12 f32) (local $a22 f32) (local $a32 f32)
    (local $a03 f32) (local $a13 f32) (local $a23 f32) (local $a33 f32)
    (local $b0 f32) (local $b1 f32) (local $b2 f32) (local $b3 f32)
    (local $r0 f32) (local $r1 f32) (local $r2 f32) (local $r3 f32)
    (local $r4 f32) (local $r5 f32) (local $r6 f32) (local $r7 f32)
    (local $r8 f32) (local $r9 f32) (local $r10 f32) (local $r11 f32)
    (local $r12 f32) (local $r13 f32) (local $r14 f32) (local $r15 f32)

    ;; Load A (a[col*4 + row] -> a_{row}{col})
    (local.set $a00 (f32.load offset=0  (local.get $a_ptr)))
    (local.set $a10 (f32.load offset=4  (local.get $a_ptr)))
    (local.set $a20 (f32.load offset=8  (local.get $a_ptr)))
    (local.set $a30 (f32.load offset=12 (local.get $a_ptr)))
    (local.set $a01 (f32.load offset=16 (local.get $a_ptr)))
    (local.set $a11 (f32.load offset=20 (local.get $a_ptr)))
    (local.set $a21 (f32.load offset=24 (local.get $a_ptr)))
    (local.set $a31 (f32.load offset=28 (local.get $a_ptr)))
    (local.set $a02 (f32.load offset=32 (local.get $a_ptr)))
    (local.set $a12 (f32.load offset=36 (local.get $a_ptr)))
    (local.set $a22 (f32.load offset=40 (local.get $a_ptr)))
    (local.set $a32 (f32.load offset=44 (local.get $a_ptr)))
    (local.set $a03 (f32.load offset=48 (local.get $a_ptr)))
    (local.set $a13 (f32.load offset=52 (local.get $a_ptr)))
    (local.set $a23 (f32.load offset=56 (local.get $a_ptr)))
    (local.set $a33 (f32.load offset=60 (local.get $a_ptr)))

    ;; Column 0 of B
    (local.set $b0 (f32.load offset=0  (local.get $b_ptr)))
    (local.set $b1 (f32.load offset=4  (local.get $b_ptr)))
    (local.set $b2 (f32.load offset=8  (local.get $b_ptr)))
    (local.set $b3 (f32.load offset=12 (local.get $b_ptr)))
    (local.set $r0 (f32.add (f32.add (f32.mul (local.get $a00) (local.get $b0)) (f32.mul (local.get $a01) (local.get $b1)))
                            (f32.add (f32.mul (local.get $a02) (local.get $b2)) (f32.mul (local.get $a03) (local.get $b3)))))
    (local.set $r1 (f32.add (f32.add (f32.mul (local.get $a10) (local.get $b0)) (f32.mul (local.get $a11) (local.get $b1)))
                            (f32.add (f32.mul (local.get $a12) (local.get $b2)) (f32.mul (local.get $a13) (local.get $b3)))))
    (local.set $r2 (f32.add (f32.add (f32.mul (local.get $a20) (local.get $b0)) (f32.mul (local.get $a21) (local.get $b1)))
                            (f32.add (f32.mul (local.get $a22) (local.get $b2)) (f32.mul (local.get $a23) (local.get $b3)))))
    (local.set $r3 (f32.add (f32.add (f32.mul (local.get $a30) (local.get $b0)) (f32.mul (local.get $a31) (local.get $b1)))
                            (f32.add (f32.mul (local.get $a32) (local.get $b2)) (f32.mul (local.get $a33) (local.get $b3)))))

    ;; Column 1 of B
    (local.set $b0 (f32.load offset=16 (local.get $b_ptr)))
    (local.set $b1 (f32.load offset=20 (local.get $b_ptr)))
    (local.set $b2 (f32.load offset=24 (local.get $b_ptr)))
    (local.set $b3 (f32.load offset=28 (local.get $b_ptr)))
    (local.set $r4 (f32.add (f32.add (f32.mul (local.get $a00) (local.get $b0)) (f32.mul (local.get $a01) (local.get $b1)))
                            (f32.add (f32.mul (local.get $a02) (local.get $b2)) (f32.mul (local.get $a03) (local.get $b3)))))
    (local.set $r5 (f32.add (f32.add (f32.mul (local.get $a10) (local.get $b0)) (f32.mul (local.get $a11) (local.get $b1)))
                            (f32.add (f32.mul (local.get $a12) (local.get $b2)) (f32.mul (local.get $a13) (local.get $b3)))))
    (local.set $r6 (f32.add (f32.add (f32.mul (local.get $a20) (local.get $b0)) (f32.mul (local.get $a21) (local.get $b1)))
                            (f32.add (f32.mul (local.get $a22) (local.get $b2)) (f32.mul (local.get $a23) (local.get $b3)))))
    (local.set $r7 (f32.add (f32.add (f32.mul (local.get $a30) (local.get $b0)) (f32.mul (local.get $a31) (local.get $b1)))
                            (f32.add (f32.mul (local.get $a32) (local.get $b2)) (f32.mul (local.get $a33) (local.get $b3)))))

    ;; Column 2 of B
    (local.set $b0 (f32.load offset=32 (local.get $b_ptr)))
    (local.set $b1 (f32.load offset=36 (local.get $b_ptr)))
    (local.set $b2 (f32.load offset=40 (local.get $b_ptr)))
    (local.set $b3 (f32.load offset=44 (local.get $b_ptr)))
    (local.set $r8  (f32.add (f32.add (f32.mul (local.get $a00) (local.get $b0)) (f32.mul (local.get $a01) (local.get $b1)))
                             (f32.add (f32.mul (local.get $a02) (local.get $b2)) (f32.mul (local.get $a03) (local.get $b3)))))
    (local.set $r9  (f32.add (f32.add (f32.mul (local.get $a10) (local.get $b0)) (f32.mul (local.get $a11) (local.get $b1)))
                             (f32.add (f32.mul (local.get $a12) (local.get $b2)) (f32.mul (local.get $a13) (local.get $b3)))))
    (local.set $r10 (f32.add (f32.add (f32.mul (local.get $a20) (local.get $b0)) (f32.mul (local.get $a21) (local.get $b1)))
                             (f32.add (f32.mul (local.get $a22) (local.get $b2)) (f32.mul (local.get $a23) (local.get $b3)))))
    (local.set $r11 (f32.add (f32.add (f32.mul (local.get $a30) (local.get $b0)) (f32.mul (local.get $a31) (local.get $b1)))
                             (f32.add (f32.mul (local.get $a32) (local.get $b2)) (f32.mul (local.get $a33) (local.get $b3)))))

    ;; Column 3 of B
    (local.set $b0 (f32.load offset=48 (local.get $b_ptr)))
    (local.set $b1 (f32.load offset=52 (local.get $b_ptr)))
    (local.set $b2 (f32.load offset=56 (local.get $b_ptr)))
    (local.set $b3 (f32.load offset=60 (local.get $b_ptr)))
    (local.set $r12 (f32.add (f32.add (f32.mul (local.get $a00) (local.get $b0)) (f32.mul (local.get $a01) (local.get $b1)))
                             (f32.add (f32.mul (local.get $a02) (local.get $b2)) (f32.mul (local.get $a03) (local.get $b3)))))
    (local.set $r13 (f32.add (f32.add (f32.mul (local.get $a10) (local.get $b0)) (f32.mul (local.get $a11) (local.get $b1)))
                             (f32.add (f32.mul (local.get $a12) (local.get $b2)) (f32.mul (local.get $a13) (local.get $b3)))))
    (local.set $r14 (f32.add (f32.add (f32.mul (local.get $a20) (local.get $b0)) (f32.mul (local.get $a21) (local.get $b1)))
                             (f32.add (f32.mul (local.get $a22) (local.get $b2)) (f32.mul (local.get $a23) (local.get $b3)))))
    (local.set $r15 (f32.add (f32.add (f32.mul (local.get $a30) (local.get $b0)) (f32.mul (local.get $a31) (local.get $b1)))
                             (f32.add (f32.mul (local.get $a32) (local.get $b2)) (f32.mul (local.get $a33) (local.get $b3)))))

    ;; Store result to out_ptr
    (f32.store offset=0  (local.get $out_ptr) (local.get $r0))
    (f32.store offset=4  (local.get $out_ptr) (local.get $r1))
    (f32.store offset=8  (local.get $out_ptr) (local.get $r2))
    (f32.store offset=12 (local.get $out_ptr) (local.get $r3))
    (f32.store offset=16 (local.get $out_ptr) (local.get $r4))
    (f32.store offset=20 (local.get $out_ptr) (local.get $r5))
    (f32.store offset=24 (local.get $out_ptr) (local.get $r6))
    (f32.store offset=28 (local.get $out_ptr) (local.get $r7))
    (f32.store offset=32 (local.get $out_ptr) (local.get $r8))
    (f32.store offset=36 (local.get $out_ptr) (local.get $r9))
    (f32.store offset=40 (local.get $out_ptr) (local.get $r10))
    (f32.store offset=44 (local.get $out_ptr) (local.get $r11))
    (f32.store offset=48 (local.get $out_ptr) (local.get $r12))
    (f32.store offset=52 (local.get $out_ptr) (local.get $r13))
    (f32.store offset=56 (local.get $out_ptr) (local.get $r14))
    (f32.store offset=60 (local.get $out_ptr) (local.get $r15))
  )

  ;; Helper to normalize and store a single frustum plane (a,b,c,d) at ptr
  (func $store_norm_plane
    (param $ptr i32) (param $a f32) (param $b f32) (param $c f32) (param $d f32)
    (local $len f32)
    (local.set $len
      (f32.sqrt
        (f32.add
          (f32.add (f32.mul (local.get $a) (local.get $a)) (f32.mul (local.get $b) (local.get $b)))
          (f32.mul (local.get $c) (local.get $c))
        )
      )
    )
    (if (f32.gt (local.get $len) (f32.const 1.0e-8))
      (then
        (local.set $a (f32.div (local.get $a) (local.get $len)))
        (local.set $b (f32.div (local.get $b) (local.get $len)))
        (local.set $c (f32.div (local.get $c) (local.get $len)))
        (local.set $d (f32.div (local.get $d) (local.get $len)))
      )
    )
    (f32.store offset=0  (local.get $ptr) (local.get $a))
    (f32.store offset=4  (local.get $ptr) (local.get $b))
    (f32.store offset=8  (local.get $ptr) (local.get $c))
    (f32.store offset=12 (local.get $ptr) (local.get $d))
  )

  ;; --------------------------------------------------------------------------
  ;; 8. frustum_extract(planes_ptr, mvp_ptr)
  ;;    Matches include/frustum_cull.h:frustum_extract (Gribb/Hartmann, 0<=z<=w).
  ;;    Writes 6 normalized vec4 planes = 24 f32 = 96 bytes at planes_ptr.
  ;; --------------------------------------------------------------------------
  (func (export "frustum_extract") (param $planes_ptr i32) (param $mvp_ptr i32)
    (local $m0 f32)  (local $m1 f32)  (local $m2 f32)  (local $m3 f32)
    (local $m4 f32)  (local $m5 f32)  (local $m6 f32)  (local $m7 f32)
    (local $m8 f32)  (local $m9 f32)  (local $m10 f32) (local $m11 f32)
    (local $m12 f32) (local $m13 f32) (local $m14 f32) (local $m15 f32)

    (local.set $m0  (f32.load offset=0  (local.get $mvp_ptr)))
    (local.set $m1  (f32.load offset=4  (local.get $mvp_ptr)))
    (local.set $m2  (f32.load offset=8  (local.get $mvp_ptr)))
    (local.set $m3  (f32.load offset=12 (local.get $mvp_ptr)))
    (local.set $m4  (f32.load offset=16 (local.get $mvp_ptr)))
    (local.set $m5  (f32.load offset=20 (local.get $mvp_ptr)))
    (local.set $m6  (f32.load offset=24 (local.get $mvp_ptr)))
    (local.set $m7  (f32.load offset=28 (local.get $mvp_ptr)))
    (local.set $m8  (f32.load offset=32 (local.get $mvp_ptr)))
    (local.set $m9  (f32.load offset=36 (local.get $mvp_ptr)))
    (local.set $m10 (f32.load offset=40 (local.get $mvp_ptr)))
    (local.set $m11 (f32.load offset=44 (local.get $mvp_ptr)))
    (local.set $m12 (f32.load offset=48 (local.get $mvp_ptr)))
    (local.set $m13 (f32.load offset=52 (local.get $mvp_ptr)))
    (local.set $m14 (f32.load offset=56 (local.get $mvp_ptr)))
    (local.set $m15 (f32.load offset=60 (local.get $mvp_ptr)))

    ;; Plane 0: Left (row3 + row0)
    (call $store_norm_plane (local.get $planes_ptr)
      (f32.add (local.get $m3)  (local.get $m0))
      (f32.add (local.get $m7)  (local.get $m4))
      (f32.add (local.get $m11) (local.get $m8))
      (f32.add (local.get $m15) (local.get $m12))
    )
    ;; Plane 1: Right (row3 - row0)
    (call $store_norm_plane (i32.add (local.get $planes_ptr) (i32.const 16))
      (f32.sub (local.get $m3)  (local.get $m0))
      (f32.sub (local.get $m7)  (local.get $m4))
      (f32.sub (local.get $m11) (local.get $m8))
      (f32.sub (local.get $m15) (local.get $m12))
    )
    ;; Plane 2: Bottom (row3 + row1)
    (call $store_norm_plane (i32.add (local.get $planes_ptr) (i32.const 32))
      (f32.add (local.get $m3)  (local.get $m1))
      (f32.add (local.get $m7)  (local.get $m5))
      (f32.add (local.get $m11) (local.get $m9))
      (f32.add (local.get $m15) (local.get $m13))
    )
    ;; Plane 3: Top (row3 - row1)
    (call $store_norm_plane (i32.add (local.get $planes_ptr) (i32.const 48))
      (f32.sub (local.get $m3)  (local.get $m1))
      (f32.sub (local.get $m7)  (local.get $m5))
      (f32.sub (local.get $m11) (local.get $m9))
      (f32.sub (local.get $m15) (local.get $m13))
    )
    ;; Plane 4: Near (row2 -> 0 <= z <= w)
    (call $store_norm_plane (i32.add (local.get $planes_ptr) (i32.const 64))
      (local.get $m2) (local.get $m6) (local.get $m10) (local.get $m14)
    )
    ;; Plane 5: Far (row3 - row2 -> z <= w)
    (call $store_norm_plane (i32.add (local.get $planes_ptr) (i32.const 80))
      (f32.sub (local.get $m3)  (local.get $m2))
      (f32.sub (local.get $m7)  (local.get $m6))
      (f32.sub (local.get $m11) (local.get $m10))
      (f32.sub (local.get $m15) (local.get $m14))
    )
  )

  ;; --------------------------------------------------------------------------
  ;; 9. cull_chunks(planes_ptr, aabbs_ptr, out_flags_ptr, count) -> i32
  ;;    Each AABB is 24 bytes (min_x, min_y, min_z, max_x, max_y, max_z).
  ;;    Writes 0/1 byte per chunk to out_flags_ptr + i, returns visible count.
  ;; --------------------------------------------------------------------------
  (func (export "cull_chunks")
    (param $planes_ptr i32)
    (param $aabbs_ptr i32)
    (param $out_flags_ptr i32)
    (param $count i32)
    (result i32)
    (local $i i32)
    (local $visible i32)
    (local $p_idx i32)
    (local $p_addr i32)
    (local $box_addr i32)
    (local $is_vis i32)
    (local $minx f32) (local $miny f32) (local $minz f32)
    (local $maxx f32) (local $maxy f32) (local $maxz f32)
    (local $pa f32) (local $pb f32) (local $pc f32) (local $pd f32)
    (local $px f32) (local $py f32) (local $pz f32)

    (if (i32.le_s (local.get $count) (i32.const 0))
      (then (return (i32.const 0)))
    )

    (local.set $i (i32.const 0))
    (local.set $visible (i32.const 0))

    (loop $chunk_loop
      (local.set $box_addr (i32.add (local.get $aabbs_ptr) (i32.mul (local.get $i) (i32.const 24))))
      (local.set $minx (f32.load offset=0  (local.get $box_addr)))
      (local.set $miny (f32.load offset=4  (local.get $box_addr)))
      (local.set $minz (f32.load offset=8  (local.get $box_addr)))
      (local.set $maxx (f32.load offset=12 (local.get $box_addr)))
      (local.set $maxy (f32.load offset=16 (local.get $box_addr)))
      (local.set $maxz (f32.load offset=20 (local.get $box_addr)))

      (local.set $is_vis (i32.const 1))
      (local.set $p_idx (i32.const 0))

      (block $plane_break
        (loop $plane_loop
          (local.set $p_addr (i32.add (local.get $planes_ptr) (i32.mul (local.get $p_idx) (i32.const 16))))
          (local.set $pa (f32.load offset=0  (local.get $p_addr)))
          (local.set $pb (f32.load offset=4  (local.get $p_addr)))
          (local.set $pc (f32.load offset=8  (local.get $p_addr)))
          (local.set $pd (f32.load offset=12 (local.get $p_addr)))

          ;; P-vertex selection matching include/frustum_cull.h:frustum_test_aabb
          (local.set $px (select (local.get $maxx) (local.get $minx) (f32.ge (local.get $pa) (f32.const 0.0))))
          (local.set $py (select (local.get $maxy) (local.get $miny) (f32.ge (local.get $pb) (f32.const 0.0))))
          (local.set $pz (select (local.get $maxz) (local.get $minz) (f32.ge (local.get $pc) (f32.const 0.0))))

          (if
            (f32.lt
              (f32.add
                (f32.add (f32.mul (local.get $pa) (local.get $px)) (f32.mul (local.get $pb) (local.get $py)))
                (f32.add (f32.mul (local.get $pc) (local.get $pz)) (local.get $pd))
              )
              (f32.const 0.0)
            )
            (then
              (local.set $is_vis (i32.const 0))
              (br $plane_break)
            )
          )

          (local.set $p_idx (i32.add (local.get $p_idx) (i32.const 1)))
          (br_if $plane_loop (i32.lt_s (local.get $p_idx) (i32.const 6)))
        )
      )

      (i32.store8 (i32.add (local.get $out_flags_ptr) (local.get $i)) (local.get $is_vis))
      (local.set $visible (i32.add (local.get $visible) (local.get $is_vis)))

      (local.set $i (i32.add (local.get $i) (i32.const 1)))
      (br_if $chunk_loop (i32.lt_s (local.get $i) (local.get $count)))
    )

    (local.get $visible)
  )

  ;; --------------------------------------------------------------------------
  ;; 10. traffic_tick(sim_time_ptr, dt) -> i32
  ;;     Increments f32 sim time at sim_time_ptr modulo 24.0s and returns phase:
  ;;       0 = NS Green  [0,  9)
  ;;       1 = NS Amber  [9, 12)
  ;;       2 = EW Green  [12, 21)
  ;;       3 = EW Amber  [21, 24)
  ;; --------------------------------------------------------------------------
  (func (export "traffic_tick") (param $sim_time_ptr i32) (param $dt f32) (result i32)
    (local $t f32)
    (local.set $t (f32.add (f32.load (local.get $sim_time_ptr)) (local.get $dt)))
    ;; Wrap modulo 24.0s
    (local.set $t
      (f32.sub
        (local.get $t)
        (f32.mul (f32.const 24.0) (f32.floor (f32.div (local.get $t) (f32.const 24.0))))
      )
    )
    (if (f32.ge (local.get $t) (f32.const 24.0))
      (then (local.set $t (f32.const 0.0)))
    )
    (if (f32.lt (local.get $t) (f32.const 0.0))
      (then (local.set $t (f32.const 0.0)))
    )
    (f32.store (local.get $sim_time_ptr) (local.get $t))

    (if (f32.lt (local.get $t) (f32.const 9.0))
      (then (return (i32.const 0)))
    )
    (if (f32.lt (local.get $t) (f32.const 12.0))
      (then (return (i32.const 1)))
    )
    (if (f32.lt (local.get $t) (f32.const 21.0))
      (then (return (i32.const 2)))
    )
    (i32.const 3)
  )
)
