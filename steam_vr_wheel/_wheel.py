from collections import deque
from math import pi, atan2, sin, cos, ceil, sqrt, acos, tan
import math

import numpy as np
import openvr
import os
import copy
import time
import threading
import random
import queue
import struct
import mmap

from . import playsound, perf_time, MEDIA_DIR, IMAGE_DATA
from steam_vr_wheel._virtualpad import VirtualPad, HandsImage
from steam_vr_wheel.pyvjoy import HID_USAGE_X, FFB_CTRL, FFBPType, FFBOP
from steam_vr_wheel.util import *
from steam_vr_wheel.i18n import _I


class HShifterImage:
    def __init__(self, wheel, x=0.25, y=-0.57, z=-0.15, degree=6, scale=100, alpha=100):
        self.vrsys = openvr.VRSystem()
        self.vroverlay = openvr.IVROverlay()

        self.x = x
        self.y = y
        self.z = z
        self.size = 14 / 100
        self.degree = degree
        self.pos = 3.5
        self.wheel = wheel
        self.config = self.wheel.config

        #self._button_queue = []
        self._snap_ctr = None
        self._snap_start_pos = False
        self._snapped = False
        self._snap_times = []
        self._snap_db_timer = None
        self._snap_ctr_offset = []
        self._snap_tf = None

        self._xz = [0,0]
        self._last_haptic_xz = [0,0]
        self._knob_pos = [0,0,0]

        self._one_tick_reset_pulse = False
        self._splitter_toggled = False
        self._range_toggled = False
        self._reverse_locked = True

        """
        |-1  | 1  | 3  | 5  | 7  |  51 43 45 47 51   R 1 3 5 R
        |-0.5| 1.5| 3.5| 5.5| 7.5|                   +-+-N-+-+
        | 0  | 2  | 4  | 6  | 8  |  51 44 46 48 51   R 2 4 6 R

        odd: towards -z
        x2 is odd: no rotation
        even: towards +z

        x = (round(pos/2)-1) * ...
        z_rot = ((pos%2 if pos%2 != 0 else 2)-1.5) * ...

        49 splitter
        50 range
        """
        self._splitter_button = 49
        self._range_button = 50
        self._pos_to_button = dict({-1:   51,   1:   43,   3:   45,   5:   47,   7:   51,
                                    -0.5: None, 1.5: None, 3.5: None, 5.5: None, 7.5: None,
                                     0:   51,   2:   44,   4:   46,   6:   48,   8:   51})
        self._pressed_button = None

        # Create
        result, self.slot = self.vroverlay.createOverlay('hshifter_slot'.encode(), 'hshifter_slot'.encode())
        check_result(result)
        result, self.stick = self.vroverlay.createOverlay('hshifter_stick'.encode(), 'hshifter_stick'.encode())
        check_result(result)
        result, self.knob = self.vroverlay.createOverlay('hshifter_knob'.encode(), 'hshifter_knob'.encode())
        check_result(result)

        # Media
        #this_dir = os.path.abspath(os.path.dirname(__file__))

        # Sound
        self._change_mp3_1 = os.path.join(MEDIA_DIR, 'shifter_change_1.mp3')
        self._change_mp3_2 = os.path.join(MEDIA_DIR, 'shifter_change_2.mp3')
        self._neutral_mp3 = os.path.join(MEDIA_DIR, 'shifter_neutral.mp3')
        self._button_mp3 = os.path.join(MEDIA_DIR, 'shifter_button.mp3')
        self._last_change_play = 0
        self._last_neutral_play = 0
        self._neutral_instances = []

        # Images
        self.slot_img = os.path.join(MEDIA_DIR, 'h_shifter_slot_7.png')
        self.slot_img_seq = os.path.join(MEDIA_DIR, 'h_shifter_slot_seq.png')
        self._stick_img = os.path.join(MEDIA_DIR, 'h_shifter_stick_low.png')
        self._stick_img_2 = os.path.join(MEDIA_DIR, 'h_shifter_stick_high.png')
        self._knob_img = os.path.join(MEDIA_DIR, 'h_shifter_knob.png')
        self._knob_img_2 = os.path.join(MEDIA_DIR, 'h_shifter_knob_over.png')

        check_result(self.vroverlay.setOverlayRaw(self.stick, *IMAGE_DATA[self._stick_img]))
        check_result(self.vroverlay.setOverlayRaw(self.knob, *IMAGE_DATA[self._knob_img]))

        # Visibility
        self._slot_v = 0.2
        check_result(self.vroverlay.setOverlayColor(self.slot, self._slot_v, self._slot_v, self._slot_v)) # default gray outline
        check_result(self.vroverlay.setOverlayAlpha(self.slot, alpha/100))
        check_result(self.vroverlay.setOverlayWidthInMeters(self.slot, self.size)) # default 14cm
        
        # Set sequential
        self.sequential = None
        self.toggle_sequential(self.config.shifter_sequential)

        # Scale
        self.rescale(scale / 100)
        stick_width = self.stick_width
        stick_height = self.stick_height
        stick_scale = self.stick_scale

        check_result(self.vroverlay.setOverlayColor(self.stick, 1, 1, 1))
        check_result(self.vroverlay.setOverlayAlpha(self.stick, alpha/100))
        check_result(self.vroverlay.setOverlayWidthInMeters(self.stick, stick_width))

        check_result(self.vroverlay.setOverlayColor(self.knob, 1, 1, 1))
        check_result(self.vroverlay.setOverlayAlpha(self.knob, alpha/100))
        check_result(self.vroverlay.setOverlayWidthInMeters(self.knob, 0.05))

        # Position
        ## Slot
        result, self.slot_tf = self.vroverlay.setOverlayTransformAbsolute(self.slot, openvr.TrackingUniverseSeated)
        check_result(result)
        result, self.slot_uv = self.vroverlay.getOverlayTextureBounds(self.slot)
        check_result(result)
        set_transform(self.slot_tf, [[1.0, 0.0, 0.0, x],
                                    [0.0, 0.0, 1.0, y],
                                    [0.0, -1.0, 0.0, z]]) # 90deg at X

        # Set reverse orientation and its position
        # _xz_rev represents where the reverse is in the coordinate system
        if self.wheel.config.shifter_reverse_orientation == "Top Left":
            self.slot_uv.vMax = 0.0
            self.slot_uv.vMin = 1.0
            self._xz_rev = [-2, -1]
        elif self.wheel.config.shifter_reverse_orientation == "Bottom Left": # default
            self._xz_rev = [-2, 1]
        elif self.wheel.config.shifter_reverse_orientation == "Top Right":
            self.slot_uv.uMax = 0.0
            self.slot_uv.uMin = 1.0
            self.slot_uv.vMax = 0.0
            self.slot_uv.vMin = 1.0
            self._xz_rev = [2, -1]
        elif self.wheel.config.shifter_reverse_orientation == "Bottom Right":
            self.slot_uv.uMax = 0.0
            self.slot_uv.uMin = 1.0
            self._xz_rev = [2, 1]

        check_result(self.vroverlay.function_table.setOverlayTextureBounds(self.slot, openvr.byref(self.slot_uv)))

        ## Knob
        result, self.knob_tf = self.vroverlay.setOverlayTransformAbsolute(self.knob, openvr.TrackingUniverseSeated)
        check_result(result)
        set_transform(self.knob_tf, [[1.0, 0.0, 0.0, x],
                                    [0.0, 1.0, 0.0, y+stick_height],
                                    [0.0, 0.0, 1.0, z]])

        # Final
        fn = self.vroverlay.function_table.setOverlayTransformAbsolute
        result = fn(self.slot, openvr.TrackingUniverseSeated, openvr.byref(self.slot_tf))
        result = fn(self.stick, openvr.TrackingUniverseSeated, openvr.byref(self.stick_tf))
        result = fn(self.knob, openvr.TrackingUniverseSeated, openvr.byref(self.knob_tf))
        check_result(self.vroverlay.showOverlay(self.slot))
        check_result(self.vroverlay.showOverlay(self.stick))
        check_result(self.vroverlay.showOverlay(self.knob))

    def tilt_delta(self, delta):
        self.degree = max(min(30, self.degree+delta), 0)

    def rescale_delta(self, delta):
        scale1 = self.stick_scale + delta
        scale1 = max(min(1.0, scale1), 0.1)
        self.rescale(scale1)

    def rescale(self, scale):

        # Stick width is always 2cm
        stick_width = 0.02
        self.stick_width = stick_width

        # Get width and height of texture
        txw, txh = IMAGE_DATA[self._stick_img][1:3]

        stick_height = txh / (txw / stick_width)
        stick_scale = scale # 1.0 => 31.65cm for default 40x633 dimension
        stick_height *= stick_scale

        self.stick_height = stick_height
        self.stick_scale = stick_scale

        ## Stick
        result, self.stick_tf = self.vroverlay.setOverlayTransformAbsolute(self.stick, openvr.TrackingUniverseSeated)
        check_result(result)
        result, self.stick_uv = self.vroverlay.getOverlayTextureBounds(self.stick)
        check_result(result)

        set_transform(self.stick_tf, [[1.0, 0.0, 0.0, self.x],
                                    [0.0, stick_scale, 0.0, self.y+stick_height/2],
                                    [0.0, 0.0, 1.0, self.z]])
        self.stick_uv.vMax = stick_scale
        check_result(self.vroverlay.function_table.setOverlayTextureBounds(self.stick, openvr.byref(self.stick_uv)))

    def check_collision(self, ctr):

        r = self.collision_radius
        p = np.array([ctr.x, ctr.y, ctr.z])
        a = np.array([self.x_stick, self.y, self.z_stick])
        b = np.array([self.x_knob, self.y_knob, self.z_knob])

        ap = p - a
        ab = b - a

        l = np.dot(ap, ab) / np.dot(ab, ab)
        l = max(0, min(1, l))
        c = a + ab * l
        cp = p - c

        d = np.sqrt(np.dot(cp, cp))
        return d <= r

    def set_stick_xz_pos(self, xz_pos, ctr=None):
        
        self.pos = xz_pos[0]*2+3 + (xz_pos[1]+1)/2

        is_button = self.pos in self._pos_to_button

        # Position that has button mapping
        if is_button:
            btn_id = self._pos_to_button[self.pos]
            self._pressed_button = btn_id

    def lock_reverse(self):
        self._reverse_locked = True

    def unlock_reverse(self):
        self._reverse_locked = False

    def toggle_sequential(self, override=None):

        if override is not None:
            if self.sequential == override:
                return
            self.sequential = override
        else:
            self.sequential = not self.sequential
        
        self.config.shifter_sequential = self.sequential

        # Reset position
        self.set_stick_xz_pos([0,0])

        if self.sequential:
            check_result(self.vroverlay.setOverlayRaw(self.slot, *IMAGE_DATA[self.slot_img_seq]))
        else:
            check_result(self.vroverlay.setOverlayRaw(self.slot, *IMAGE_DATA[self.slot_img]))


    def toggle_splitter(self, ctr):

        self._splitter_toggled = not self._splitter_toggled
        
        check_result(self.vroverlay.setOverlayRaw(self.knob, 
            *IMAGE_DATA[self._knob_img_2 if self._splitter_toggled else self._knob_img]))
        
        playsound(self._button_mp3, block=False, volume=self.config.sfx_volume/100)
        ctr.haptic([None, 0.6], [0.1, None], [None, 0.6])

    def toggle_range(self, ctr, override=None):

        if override is not None:
            if self._range_toggled == override:
                return
            self._range_toggled = override
        else:
            self._range_toggled = not self._range_toggled
            
        playsound(self._button_mp3, block=False, volume=self.config.sfx_volume/100)

        if self._range_toggled:
            check_result(self.vroverlay.setOverlayRaw(self.stick, *IMAGE_DATA[self._stick_img_2]))
            ctr.haptic([0.3, lambda t: t**3])
        else:
            check_result(self.vroverlay.setOverlayRaw(self.stick, *IMAGE_DATA[self._stick_img]))
            ctr.haptic([0.3, lambda t: 0.2 * (1-t**2)])

    def snap_ctr(self, ctr):
        now = time.time()
        self._snap_ctr = ctr
        self._snap_ctr_offset = [ctr.x - self._knob_pos[0], ctr.y - self._knob_pos[1], ctr.z - self._knob_pos[2]]
        self._snapped = True

        # Reset 
        self._last_haptic_xz = [0,0]

        # Check double tap
        self._snap_times.append(now)
        self._snap_times = self._snap_times[-2:]

        if len(self._snap_times) >= 2 and self._snap_times[-1] - self._snap_times[-2] <= 0.5:
            self._reset_double_tap()
            self.toggle_splitter(ctr)

    def unsnap(self):
        self._snapped = False

        if self.sequential:
            if self.pos != 3.5:
                self._neutral_instances.append(playsound(self._neutral_mp3,
                    block=False,
                    volume=self.config.sfx_volume/100))

            self.set_stick_xz_pos([0,0])
        else:
            if self._pressed_button is None:
                self.set_stick_xz_pos([0,0])

        self._move_stick(self._xz_pos())

    def _xz_pos(self):
        # Convert pos to x and z
        return [(ceil(self.pos/2)-2), ((self.pos%2 if self.pos%2 != 0 else 2)-1.5)*2]

    def _move_stick(self, xz):
        self._xz = xz

    def render(self, hmd, xz_override=None):
        # xz = relative and normalized
        xz = self._xz

        if xz_override is not None:
            xz = xz_override # This is for previewing the angle changes in edit mode

        unit = (self.size/4 - self.stick_width/2)

        x_deg = self.degree * abs(xz[0])
        z_deg = self.degree * abs(xz[1])
        x_sin = sin(x_deg*pi/180) * self.stick_height
        z_sin = sin(z_deg*pi/180) * self.stick_height
        x_knob = self.x + xz[0] * unit + x_sin * (-1 if xz[0] < 0 else 1)
        z_knob = self.z + xz[1] * unit + z_sin * (-1 if xz[1] < 0 else 1)
        x_stick = self.x + xz[0] * unit
        z_stick = self.z + xz[1] * unit

        # 
        a = atan2(x_knob-hmd.x, z_knob-hmd.z)
        yaw = a / pi * 180 + 180
        
        rot_knob = rotation_matrix(0, yaw, 0)
        rot_stick = rotation_matrix(z_deg * (-1 if xz[1] < 0 else 1), 0, -x_deg * (-1 if xz[0] < 0 else 1))

        y_knob = (self.y + self.stick_height - 
            (abs(xz[1])*((1-cos((z_deg)*pi/180))*self.stick_height)) -
            (abs(xz[0])*((1-cos((x_deg)*pi/180))*self.stick_height))
            )

        def rot_dot_tf(rot, hmd34, local=None):
            tf = np.eye(4)
            for i in range(3):
                tf[i][3] = hmd34[i][3] # discard original rot

            r = np.eye(4)
            r[0:3, 0:3] = rot
            d = np.dot(tf, r)

            if local is not None:
                r[0:3, 0:3] = local
                d = np.dot(d, r)

            for i in range(3):
                for j in range(4):
                    hmd34[i][j] = d[i,j]

        self._knob_pos[0] = x_knob
        self._knob_pos[1] = y_knob
        self._knob_pos[2] = z_knob
        self.knob_tf[0][3] = x_knob
        self.knob_tf[1][3] = y_knob
        self.knob_tf[2][3] = z_knob
        rot_dot_tf(rot_knob, self.knob_tf)

        offset_stick = np.dot(rot_stick, (0, self.stick_height/2, 0))
        self.stick_tf[0][3] = x_stick + offset_stick[0]
        self.stick_tf[1][3] = self.y + offset_stick[1]
        self.stick_tf[2][3] = z_stick + offset_stick[2]
        scale_stick = np.eye(3)
        scale_stick[2,2] = self.stick_scale
        local_stick = np.dot(scale_stick, rot_knob) 
        rot_dot_tf(rot_stick, self.stick_tf, local_stick)

        self.slot_tf[0][3] = self.x
        self.slot_tf[1][3] = self.y
        self.slot_tf[2][3] = self.z

        # Bounds
        coll_radius = 0.06 # 6cm radius for collision; collision shape is capsule
        self.collision_radius = coll_radius

        self.x_knob = x_knob
        self.y_knob = y_knob
        self.z_knob = z_knob
        self.x_stick = x_stick
        self.z_stick = z_stick

        # Set snap transform
        ctr = self._snap_ctr
        self._snap_tf = openvr.HmdMatrix34_t()
        self._snap_tf[0][3] = x_knob
        self._snap_tf[1][3] = y_knob
        self._snap_tf[2][3] = z_knob
        rot_dot_tf(rot_knob, self._snap_tf)

        fn = self.vroverlay.function_table.setOverlayTransformAbsolute
        fn(self.slot, openvr.TrackingUniverseSeated, openvr.byref(self.slot_tf))
        fn(self.stick, openvr.TrackingUniverseSeated, openvr.byref(self.stick_tf))
        fn(self.knob, openvr.TrackingUniverseSeated, openvr.byref(self.knob_tf))

    def attach_hand(self, hand, left_ctr=None, right_ctr=None):
        self.wheel.hands_overlay.move(hand, self._snap_tf)

    def set_color(self, cl):
        check_result(self.vroverlay.setOverlayColor(self.knob, *cl))
        check_result(self.vroverlay.setOverlayColor(self.stick, *cl))
        
        cl_s = [a*self._slot_v for a in cl]
        check_result(self.vroverlay.setOverlayColor(self.slot, *cl_s))

    def set_alpha(self, alpha):
        check_result(self.vroverlay.setOverlayAlpha(self.knob, alpha))
        check_result(self.vroverlay.setOverlayAlpha(self.stick, alpha))
        check_result(self.vroverlay.setOverlayAlpha(self.slot, alpha))

    def move_delta(self, d):
        self.x += d[0]
        self.y += d[1]
        self.z += d[2]
        self.wheel.config.shifter_center = [self.x, self.y, self.z]

    def update(self):

        if self._one_tick_reset_pulse:
            self._one_tick_reset_pulse = False
            for v in self._pos_to_button.values():
                if v is not None:
                    self.wheel.set_button(v, False)

            self.wheel.set_button(self._splitter_button, not self._splitter_toggled)
            self.wheel.set_button(self._range_button, not self._range_toggled)

            return

        for v in self._pos_to_button.values():
            if v != self._pressed_button and v is not None:
                self.wheel.set_button(v, False)
        if self._pressed_button is not None:
            self.wheel.set_button(self._pressed_button, True)

        now = time.time()

        # Toggles
        self.wheel.set_button(self._splitter_button, self._splitter_toggled)
        self.wheel.set_button(self._range_button, self._range_toggled)

        if self._snapped:
            u_sin = (self.stick_height * sin(self.degree*pi/180))
            unit = (self.size/4 - self.stick_width/2)

            ctr = self._snap_ctr
            p1 = [ctr.x, ctr.y, ctr.z]
            p1[0] -= self._snap_ctr_offset[0]
            #p1[1] -= self._snap_ctr_offset[1]
            p1[2] -= self._snap_ctr_offset[2]

            # Unsafe position
            dp_unsafe = (p1[0]-self.x, 0, p1[2]-self.z)
            dp_unsafe = [dp_unsafe[0] / (u_sin + unit),
                        0,
                        dp_unsafe[2] / (u_sin + unit)]

            # Sequential
            if self.sequential:
                dp_unsafe[0] = 0 # Drop x

            # Consider reverse
            if self._xz_rev[0] == -2:
                # Left side reverse
                # clamp x [-2, 1]
                xz_ctr = np.array([
                    max(min(dp_unsafe[0], 1.0), -2.0),
                    max(min(dp_unsafe[2], 1.0), -1.0)])
            else:
                # Right side reverse
                # clamp x [-1, 2]
                xz_ctr = np.array([
                    max(min(dp_unsafe[0], 2.0), -1.0),
                    max(min(dp_unsafe[2], 1.0), -1.0)])

            # Top-bottom side clamper
            # Top side = min
            # Bottom side = max
            xz_rev_z_clamper = max if self._xz_rev[1] == 1 else min

            x_mid_margin = 0.55
            z_end_margin = 0.8
            z_mid_margin = 0.55

            in_middle = abs(xz_ctr[1]) <= z_mid_margin

            xz_pos_0 = self._xz_pos()
            xz_pos_1 = xz_pos_0.copy()
            xz_0 = self._xz
            xz_1 = xz_0.copy()
            if in_middle:
                xz_pos_1[1] = 0 # Set to Neutral

                xz_1[0] = xz_ctr[0]
                xz_1[1] = xz_ctr[1]
                abs_xz_ctr_0 = abs(xz_ctr[0])
                if abs_xz_ctr_0 >= 1:
                    if xz_ctr[0] * self._xz_rev[0] > 0:
                        xz_rev_0__2 = self._xz_rev[0]/2

                        if self._reverse_locked and xz_pos_0[0] != self._xz_rev[0]:
                            xz_1[0] = xz_rev_0__2
                            xz_pos_1[0] = xz_rev_0__2
                        else:
                            if abs_xz_ctr_0 < 2:
                                xz_1[1] = 0

                                xz_pos_1[0] = xz_rev_0__2
                            else:
                                xz_1[1] = xz_rev_z_clamper(0, xz_1[1])

                                xz_pos_1[0] = self._xz_rev[0]
                    else:
                        s = 1
                        if xz_ctr[0] < 0:
                            s = -1
                        xz_1[0] = s
                        xz_pos_1[0] = s
                elif abs(xz_ctr[0]) <= x_mid_margin:
                    if abs(xz_ctr[0]) < abs(xz_ctr[1]):
                        xz_1[0] = 0
                    else:
                        xz_1[1] = 0
                    xz_pos_1[0] = 0
                else:
                    xz_1[1] = 0
            else:
                xz_1[0] = xz_pos_0[0]

                if xz_pos_0[0] == self._xz_rev[0]: # reverse
                    xz_1[1] = xz_rev_z_clamper(0, xz_ctr[1])
                    if self._xz_rev[1] == 1:
                        if xz_ctr[1] > z_end_margin:
                            xz_pos_1[1] = 1
                        else:
                            pass
                            #xz_pos_1[1] = 0
                    else:
                        if xz_ctr[1] < -z_end_margin:
                            xz_pos_1[1] = -1
                        else:
                            pass
                            #xz_pos_1[1] = 0

                else:
                    xz_1[1] = xz_ctr[1]
                    if xz_ctr[1] < -z_end_margin:
                        xz_pos_1[1] = -1
                    elif xz_ctr[1] > z_end_margin:
                        xz_pos_1[1] = 1
                    else:
                        pass
                        #xz_pos_1[1] = 0

            # Restrain haptic
            restrained_margin = 2 # note that this is proportional value not 2 meters
            r_var1 = abs(dp_unsafe[0]-xz_pos_1[0])
            r_var2 = abs(dp_unsafe[2]-xz_pos_1[1])
            for rv in (r_var1, r_var2):
                if rv > restrained_margin:
                    h = (rv-restrained_margin) / 1.5
                    h = min(1, h)
                    ctr.haptic([None, h])
                    break

            hpt_xz = self._last_haptic_xz

            # Check gear changed or else check hapitc
            if xz_pos_0 != xz_pos_1:
                # Position changed
                # Reset double tap in order to prevent triggering splitter during fast gear change
                self._reset_double_tap()

                # Gear changed
                if xz_pos_1[1] != 0:
                    #openvr.VRSystem().triggerHapticPulse(ctr.id, 0, 3000)
                    #ctr.haptic([0.3, lambda t: 1.0 if t < 0.1 else math.exp(-10*(t-0.1)) if t < 1 else 0.0])

                    # TODO: this part is in the test phase
                    #       this is to counteract the issue where you alt-tab or do something to lose focus from ETS2,
                    #       the game resets the splitter and range to off even though the toggle is on
                    self._one_tick_reset_pulse = True

                    if now - self._last_change_play > 0.07:

                        # Cancel playing of neutral instances so that the user won't hear it
                        for i in self._neutral_instances:
                            playsound(None, stop_alias=i)
                        self._neutral_instances = []

                        playsound(self._change_mp3_2 if xz_pos_1[1] == -1 else self._change_mp3_1,
                            block=False,
                            volume=self.config.sfx_volume/100)

                        self._last_change_play = now

                elif xz_pos_1[1] == 0: # Move to the middle row

                    if self.sequential:
                        # Notify the user of netural when in sequential mode
                        ctr.haptic([None, 1])

                    if now - self._last_neutral_play > 0.16:
                        self._neutral_instances.append(playsound(self._neutral_mp3,
                            block=False,
                            volume=self.config.sfx_volume/100))

                    self._last_neutral_play = now

            elif abs(hpt_xz[0] - xz_1[0]) > 0.35 or abs(hpt_xz[1] - xz_1[1]) > 0.35: # Check haptic

                self._last_haptic_xz = xz_1.copy()

                # Play haptic when the stick is moving in the slot
                #openvr.VRSystem().triggerHapticPulse(ctr.id, 0, 1500)

            self._move_stick(xz_1)
            self.set_stick_xz_pos(xz_pos_1)


    def _reset_double_tap(self):
        self._snap_times = []



class SteeringWheelImage:
    def __init__(self, x=0, y=-0.4, z=-0.35, size=0.55, alpha=1):
        self.vrsys = openvr.VRSystem()
        self.vroverlay = openvr.IVROverlay()
        result, self.wheel = self.vroverlay.createOverlay('keyiiii'.encode(), 'keyiiii'.encode())
        check_result(result)

        check_result(self.vroverlay.setOverlayColor(self.wheel, 1, 1, 1))
        check_result(self.vroverlay.setOverlayAlpha(self.wheel, alpha))
        check_result(self.vroverlay.setOverlayWidthInMeters(self.wheel, size))

        #this_dir = os.path.abspath(os.path.dirname(__file__))
        wheel_img = os.path.join(MEDIA_DIR, 'steering_wheel.png')

        check_result(self.vroverlay.setOverlayRaw(self.wheel, *IMAGE_DATA[wheel_img]))


        result, transform = self.vroverlay.setOverlayTransformAbsolute(self.wheel, openvr.TrackingUniverseSeated)

        transform[0][0] = 1.0
        transform[0][1] = 0.0
        transform[0][2] = 0.0
        transform[0][3] = x

        transform[1][0] = 0.0
        transform[1][1] = 1.0
        transform[1][2] = 0.0
        transform[1][3] = y

        transform[2][0] = 0.0
        transform[2][1] = 0.0
        transform[2][2] = 1.0
        transform[2][3] = z

        self.transform = transform
        self.size = size

        fn = self.vroverlay.function_table.setOverlayTransformAbsolute
        pmatTrackingOriginToOverlayTransform = transform
        result = fn(self.wheel, openvr.TrackingUniverseSeated, openvr.byref(pmatTrackingOriginToOverlayTransform))

        check_result(result)
        check_result(self.vroverlay.showOverlay(self.wheel))

    def set_color(self, cl):
        check_result(self.vroverlay.setOverlayColor(self.wheel, *cl))

    def set_alpha(self, alpha):
        check_result(self.vroverlay.setOverlayAlpha(self.wheel, alpha))

    def move_rotate(self, pos=None, size=None, pitch_roll=None):
        if pos is not None:
            self.transform[0][3] = pos.x
            self.transform[1][3] = pos.y
            self.transform[2][3] = pos.z

        if pitch_roll is not None:
            r = rotation_matrix(-pitch_roll[0], 0, pitch_roll[1])
            for i in range(3):
                for j in range(3):
                    self.transform[i][j] = r[i,j]

        fn = self.vroverlay.function_table.setOverlayTransformAbsolute
        fn(self.wheel, openvr.TrackingUniverseSeated, openvr.byref(self.transform))

        if size is not None:
            self.size = size
            check_result(self.vroverlay.setOverlayWidthInMeters(self.wheel, size))

    def hide(self):
        check_result(self.vroverlay.hideOverlay(self.wheel))

    def show(self):
        check_result(self.vroverlay.showOverlay(self.wheel))



class GrabControllerPoint(Point):
    def __init__(self, x, y, z, id=0):
        super().__init__(x, y, z)
        self.id = id


class Wheel(VirtualPad):
    def __init__(self, inertia=0.95, center_speed=pi/180):
        super().__init__()

        print(_I("intro.wheel"))

        self.vrsys = openvr.VRSystem()
        self.hands_overlay = None
        self.is_edit_mode = False
        x, y, z = self.config.wheel_center
        size = self.config.wheel_size
        self._inertia = inertia
        self._center_speed = center_speed  # radians per frame, force which returns wheel to center when not grabbed
        self._center_speed_ffb_mags = np.zeros(60)

        # FFB
        if self.config.wheel_ffb:
            self.ffb_paused = False
            self.device.ffb_callback(self.ffb_callback)

        self.x = 0  # -1 0 1
        self._wheel_angles = deque(maxlen=10)
        self._wheel_angles.append(0)
        self._wheel_angles.append(0)
        self._snapped = False

        self._rot = rotation_matrix(-self.config.wheel_pitch, 0, 0)
        self._rot_inv = rotation_matrix(self.config.wheel_pitch, 0, 0)

        # Center crossing smoothing
        self._last_non_centerlimit_pos = None
        self._centerlimit_radius = 0.08

        # radians per frame last turn speed when wheel was being held, gradually decreases after wheel is released
        self._turn_speed = 0

        self.wheel_image = SteeringWheelImage(x=x, y=y, z=z, size=size, alpha=self.config.wheel_alpha)
        self.center = Point(x, y, z)
        self.size = size
        self._grab_started_point = None
        self._wheel_grab_offset = 0

        # for manual grab:
        self._grip_queue = queue.Queue()
        self._hand_snaps = dict({'left': '', 'right': ''})

        # for auto grab
        self._last_left_in_holding = False
        self._last_right_in_holding = False

        # H Shifter
        s_c = self.config.shifter_center
        self.h_shifter_image = HShifterImage(self, x=s_c[0], y=s_c[1], z=s_c[2],
                            alpha=self.config.shifter_alpha,
                            scale=self.config.shifter_scale,
                            degree=self.config.shifter_degree)
        self._shifter_button_lock = threading.Lock()

        # (ETS2)
        self._ets2_last_hand_cl = 1

    def ffb_callback(self, data):

        now = time.time()
        if hasattr(self, "_ffb_last_now") == False:
            self._ffb_last_now = now
            self._ffb_gain_coef = 1.0
            self._ffb_effects = dict()

            self._ffb_test_dir_map = dict()
            self._ffb_test_t = now - 20.0
            self._ffb_test_unhandled = dict()
            self._ffb_test_handled = dict()

        class Effect:
            start = 0
            data = dict()

        def norm_gain(g):
            g /= 0xFF
            return g

        def _ffb_test_f(handled, t, sub=None):
            k = str(t)
            if sub is not None:
                k += "-" + str(sub)

            d = self._ffb_test_handled if handled else self._ffb_test_unhandled
            if not k in d:
                d[k] = 0
            d[k] += 1

        # Elapsed and frequency
        elapsed = now-self._ffb_last_now
        self._ffb_last_now = now
        
        # Handle raw data
        if True:

            typ = data['Type']

            # Effect
            effect = None
            ebi = None
            if "EBI" in data:
                ebi = data["EBI"]
                if ebi in self._ffb_effects:
                    effect = self._ffb_effects[ebi]
                else:
                    effect = Effect()
                    self._ffb_effects[ebi] = effect
            
            # Gain
            if typ == FFBPType.PT_GAINREP:
                self._ffb_gain_coef = norm_gain(data['Gain'])
                #print(f"New global FFB gain coefficient is {self._ffb_gain_coef} raw gain is {data['Gain']}")

                _ffb_test_f(True, typ)

            #FFBPType.PT_EFOPREP 10
            elif typ == FFBPType.PT_EFOPREP:
                op = data['EffOp']['EffectOp']
                if op == FFBOP.EFF_START or op == FFBOP.EFF_SOLO:

                    effect.start = now
                    effect.data.update(data)
                    _ffb_test_f(True, FFBPType.PT_EFOPREP, op)

                elif op == FFBOP.EFF_STOP:

                    del self._ffb_effects[ebi]
                    _ffb_test_f(True, FFBPType.PT_EFOPREP, op)

            #FFBPType.PT_EFFREP
            elif typ == FFBPType.PT_EFFREP:

                effect.data.update(data)

                # [TEST] Dir map
                rep = data["Eff_Report"]
                self._ffb_test_dir_map["DirX %d" % rep["DirX"]] = 0
                self._ffb_test_dir_map["Direction %d" % rep["Direction"]] = 0

                _ffb_test_f(True, FFBPType.PT_EFFREP)

            #FFBPType.PT_CONSTREP
            elif typ == FFBPType.PT_CONSTREP:

                effect.data.update(data)
                _ffb_test_f(True, FFBPType.PT_CONSTREP)
            
            #FFBPType.PT_PRIDREP
            elif typ == FFBPType.PT_PRIDREP:
                _ffb_test_f(False, FFBPType.PT_PRIDREP)

            #FFBPType.PT_CTRLREP
            elif typ == FFBPType.PT_CTRLREP:
                ctrl = data['DevCtrl']
                if ctrl in [FFB_CTRL.CTRL_STOPALL, FFB_CTRL.CTRL_DEVRST]:

                    self._center_speed_ffb_mags[:] = 0
                    self._ffb_effects = dict()

                    _ffb_test_f(True, FFBPType.PT_CTRLREP, ctrl)

                elif ctrl == FFB_CTRL.CTRL_DEVPAUSE:

                    self.ffb_paused = True
                    self._ffb_pause_start = now

                    _ffb_test_f(True, FFBPType.PT_CTRLREP, ctrl)

                elif ctrl == FFB_CTRL.CTRL_DEVCONT:
                    self.ffb_paused = False

                    since_pause = now - self._ffb_pause_start

                    for v in self._ffb_effects.values():
                        v.start += since_pause

                    _ffb_test_f(True, FFBPType.PT_CTRLREP, ctrl)
                else:
                    _ffb_test_f(False, FFBPType.PT_CTRLREP, ctrl)

            else:
                """
                if typ not in [
                    FFBPType.PT_CONSTREP,
                    FFBPType.PT_CTRLREP,
                    FFBPType.PT_EFOPREP,
                    FFBPType.PT_CONDREP,
                    FFBPType.PT_PRIDREP,
                    FFBPType.PT_EFFREP,
                    FFBPType.PT_GAINREP,
                    ]:
                """
                _ffb_test_f(False, typ)

        if False: #now - self._ffb_test_t > 30.0:
            '''
            [TEST] FFB behaviors
            NO  {'17': 1, '11': 1}
            YES {'12-3': 2, '12-4': 2, '13': 1, '5': 22659, '1': 22548, '10-1': 22547, '10-3': 104}
            Dir {'DirX 63': 0, 'Direction 63': 0}
            '''
            
            print("[TEST] FFB behaviors",
                "\n  NO ", self._ffb_test_unhandled,
                "\n  YES", self._ffb_test_handled,
                "\n  Dir", self._ffb_test_dir_map)
            self._ffb_test_t = now

        
        # Calc magnitude
        sum_m = 0
        if self.ffb_paused == False:
            
            solo = False
            for k in list(self._ffb_effects.keys()):
                e = self._ffb_effects[k]
                d = e.data

                # Check if effect is ended
                ended = False
                lc = deep_get(d, ["EffOp", "LoopCount"])
                if lc == None:
                    pass
                elif lc == 0:
                    pass
                elif lc > 0:
                    duration = deep_get(d, ["Eff_Report", "Duration"])

                    if duration == 0xFFFF:
                        pass
                    elif duration == None:
                        pass
                    else:
                        ended = now > e.start + lc * duration/1000.0

                if ended:
                    del self._ffb_effects[k]
                    continue

                if solo:
                    continue

                # Get magnitude per effect type
                m = 0
                if "Eff_Constant" in d:
                    m = d['Eff_Constant']['Magnitude'] / 10000.0

                # Get Coef and consider its own gain
                own_coef = deep_get(d, ["Eff_Report", "Gain"], 0xFF)
                own_coef = norm_gain(own_coef)
                coef = self._ffb_gain_coef * own_coef 

                # Sum
                m *= coef 
                sum_m += m

                # If solo effect, remove other effects' influence
                if deep_get(d, ["EffOp", "EffectOp"]) == FFBOP.EFF_SOLO:
                    sum_m = m
                    solo = True

            # Make value smooth overall
            prev_m = self._center_speed_ffb_mags[0]
            alpha = 0.3
            smoothed_m = alpha * sum_m + (1 - alpha) * prev_m

            self._center_speed_ffb_mags[1:] = self._center_speed_ffb_mags[:-1]
            self._center_speed_ffb_mags[0] = smoothed_m


    def point_in_holding_bounds(self, point):
        # Checking for auto grabbing
        point = self.to_wheel_space(point)

        a = self.size/2 + 0.06
        b = self.size/2 - 0.10

        x = point.x - self.center.x
        y = point.y - self.center.y
        z = point.z - self.center.z

        if abs(z) < 0.075:
            distance = sqrt(x**2+y**2)
            if distance < b:
                return False
            if distance < a:
                return True
        else:
            return False

    def _subtract_and_rotate(self, point, mat):

        diff = np.array([point.x-self.center.x,
                        point.y-self.center.y,
                        point.z-self.center.z])
        l = np.dot(mat, diff)
        l[0] += self.center.x
        l[1] += self.center.y
        l[2] += self.center.z
        return Point(l[0], l[1], l[2])

    def to_wheel_space(self, point):
        return self._subtract_and_rotate(point, self._rot_inv)

    def to_absolute_space(self, point):
        return self._subtract_and_rotate(point, self._rot)

    def unwrap_wheel_angles(self):
        period = 2 * pi
        angle = np.array(self._wheel_angles, dtype=float)
        diff = np.diff(angle)
        diff_to_correct = (diff + period / 2.) % period - period / 2.
        increment = np.cumsum(diff_to_correct - diff)
        angle[1:] += increment
        self._wheel_angles[-1] = angle[-1]

    def wheel_raw_angle(self, point):

        point = self.to_wheel_space(point)
        a = float(point.y) - self.center.y
        b = float(point.x) - self.center.x

        angle = atan2(a, b)
        return angle

    def wheel_double_raw_angle(self, left_ctr, right_ctr):
        left_ctr = self.to_wheel_space(left_ctr)
        right_ctr = self.to_wheel_space(right_ctr)
        a = left_ctr.y - right_ctr.y
        b = left_ctr.x - right_ctr.x

        return atan2(a, b)

    def ready_to_unsnap(self, l, r):
        l = self.to_wheel_space(l)
        r = self.to_wheel_space(r)

        d = (l.x - r.x)**2 + (l.y - r.y)**2 + (l.z - r.z)**2

        if d > self.size**2:
            return True

        dc = ((self.center.x - (l.x+r.x)/2)**2
              + (self.center.y - (l.y+r.y)/2)**2
              + (self.center.z - (l.z+r.z)/2)**2
              )
        if dc > self.size**2:
            return True

        return False

    def set_button_unpress(self, button, hand):
        super().set_button_unpress(button, hand)

        if self.config.wheel_grabbed_by_grip_toggle: # TODO fix name. True means it is toggle
            if button == openvr.k_EButton_Grip and hand == 'left':
                self._grip_queue.put(['left', False])

            if button == openvr.k_EButton_Grip and hand == 'right':
                self._grip_queue.put(['right', False])
        else:
            pass

    def set_button_press(self, button, hand, left_ctr, right_ctr):
        super().set_button_press(button, hand, left_ctr, right_ctr)
        
        ctr = left_ctr if hand == 'left' else right_ctr

        if self._hand_snaps[hand] == 'shifter':
            if button == openvr.k_EButton_A: # A
                self.h_shifter_image.toggle_splitter(ctr)

        if button == openvr.k_EButton_Grip and hand == 'left':
            if self.config.wheel_grabbed_by_grip_toggle: # TODO fix name. True means it is toggle
                self._grip_queue.put(['left', True])
            else:
                self._grip_queue.put(['left', self._hand_snaps['left'] == ''])

        if button == openvr.k_EButton_Grip and hand == 'right':
            if self.config.wheel_grabbed_by_grip_toggle:
                self._grip_queue.put(['right', True])
            else:
                self._grip_queue.put(['right', self._hand_snaps['right'] == ''])


    def _wheel_update(self, left_ctr, right_ctr):
        left_bound = self._hand_snaps['left'][:5] == 'wheel'
        right_bound = self._hand_snaps['right'][:5] == 'wheel'

        if right_bound and left_bound and not self._snapped:
            self.is_held([left_ctr, right_ctr])

        if self._snapped: # Both hands attached
            self._last_non_centerlimit_pos = None # Remove the pivot point

            angle = self.wheel_double_raw_angle(left_ctr, right_ctr) + self._wheel_grab_offset
            return angle

        if right_bound:
            controller = right_ctr
            self.is_held(controller)
        elif left_bound:
            controller = left_ctr
            self.is_held(controller)
        else: # No hands
            self._last_non_centerlimit_pos = None # Remove the pivot point

            self.is_not_held()
            return None
        
        # Prevent abrupt turn when the hand goes across the center
        raw_angle = self.wheel_raw_angle(controller)
        ctr_wheel = self.to_wheel_space(controller)
        l = sqrt((self.center.x-ctr_wheel.x)**2+
                (self.center.y-ctr_wheel.y)**2)
        limit = self._centerlimit_radius # 0.08 = 8cm from center

        if l <= limit:
            if self._last_non_centerlimit_pos is None:
                # Pivot point has to be reset when the number of attached hands is no longer 1 (that is, 0 or 2)
                # otherwise, it turns abruptly when a new one-hand grab starts in a constrained area because the pivot point is irrelevantly set
                self._last_non_centerlimit_pos = Point(controller.x, controller.y, controller.z)

            pivot_angle = self.wheel_raw_angle(self._last_non_centerlimit_pos)
            d = ((raw_angle - pivot_angle) + pi) % (2*pi) - pi
            raw_angle = pivot_angle + d * (l/limit)**2
        else:
            # Update the pivot point while the hand is grabbing the wheel and outside the constrained area
            self._last_non_centerlimit_pos = Point(controller.x, controller.y, controller.z)

        angle = raw_angle + self._wheel_grab_offset
        return angle

    def calculate_grab_offset(self, raw_angle=None):

        # Calculates the angular offset from raw_angle to the most recent angle of wheel

        if raw_angle is None:
            raw_angle = self.wheel_raw_angle(self._grab_started_point)
        self._wheel_grab_offset = self._wheel_angles[-1] - raw_angle

    def is_held(self, controller):

        # is_held, NOT like its name, puts the passed controllers into "held" state
        # TODO make this set_held or revise how held state is handled

        if isinstance(controller, list):
            self._snapped = True
            angle = self.wheel_double_raw_angle(controller[0], controller[1])
            self.calculate_grab_offset(angle)
            self._grab_started_point = None
            return

        if self._grab_started_point is None or self._grab_started_point.id != controller.id:
            self._grab_started_point = GrabControllerPoint(controller.x, controller.y, controller.z, controller.id)
            self.calculate_grab_offset()

    def is_not_held(self):

        # is_not_held, NOT like its name, manages "not_held" state
        # self._grab_started_point = None doesn't mean it is completely not held
        # it can be either no hands or TWO HANDS all attached to the wheel if you confer the above function 'is_held'
        # TODO revise how it is handled

        self._grab_started_point = None

    def inertia(self):

        # inertia simulates inertia done to the wheel

        if self._grab_started_point:
            self._turn_speed = self._wheel_angles[-1] - self._wheel_angles[-2]
        else:
            self._wheel_angles.append(self._wheel_angles[-1] + self._turn_speed)
            self._turn_speed *= self._inertia

    def center_force(self):
        
        # center_force handles the centering of the wheel to its center position
        # user can use FFB to get the actual force done to the wheel
        # FFB is tested working on Euro Truck Simulator 2 only

        now = time.time()

        if self.config.wheel_ffb:
            # FFB
            epsilon = 0
            if self.ffb_paused == False:
                epsilon = self._center_speed * self.config.wheel_centerforce
                epsilon *= 0.6 # x0.6 to make the default value of 100 of wheel_centerforce is
                               # a moderate value for centering the wheel
                epsilon *= self._center_speed_ffb_mags[0]

            self._wheel_angles.append(self._wheel_angles[-1] + epsilon)

        else:
            # NO ffb
            epsilon = self._center_speed * self.config.wheel_centerforce
            epsilon *= 0.04 # roughly 15 times difference between FFB and non FFB to make it kind of
                            # similar for same center force value

            angle = self._wheel_angles[-1]
            if abs(angle) < epsilon:
                self._wheel_angles[-1] = 0
                return

            if angle < 0:
                epsilon *= -1
            self._wheel_angles[-1] -= epsilon

    def send_to_vjoy(self):
        wheel_turn = self._wheel_angles[-1] / (2 * pi)
        axisX = int((-wheel_turn / (self.config.wheel_degrees / 360) + 0.5) * 0x8000)
        self.set_axis(HID_USAGE_X, axisX)

    def render(self, hmd):

        self.wheel_image.move_rotate(
            pos=self.center,
            pitch_roll=[
            self.config.wheel_pitch,
            self._wheel_angles[-1]/pi*180
            ])

        alpha = self.config.wheel_alpha / 100.0

        d = sqrt((self.center.x-hmd.x)**2+
                    (self.center.y-hmd.y)**2+
                    (self.center.z-hmd.z)**2)
        if d == 0: # Prevent div by 0
            d = 0.001

        p2 = hmd.normal.copy() * d
        pc_d = sqrt((self.center.x-p2[0])**2+
                    (self.center.y-p2[1])**2+
                    (self.center.z-p2[2])**2)
        a = min(1.0, max(-1.0, -((pc_d/d)**2/2-1)))
        th = acos(a)

        if self.config.wheel_transparent_center:
            if th < pi/2:
                a = tan(th)*d
                t0 = self.size/2
                t1 = self.size
                if a <= t0:
                    alpha = 0.0
                elif a <= t1:
                    alpha *= (a-t0)/(t1-t0)

        self.wheel_image.set_alpha(alpha)

    def limiter(self, left_ctr, right_ctr):
        if abs(self._wheel_angles[-1])/(2*pi)>(self.config.wheel_degrees / 360)/2:
            self._wheel_angles[-1] = self._wheel_angles[-2]

            sign = 1
            if self._wheel_angles[-1] < 0:
                sign = -1
            self._turn_speed = -0.005 * sign

            left_bound = self._hand_snaps['left'][:5] == 'wheel'
            right_bound = self._hand_snaps['right'][:5] == 'wheel'
            if left_bound:
                left_ctr.haptic([None, 1])
            if right_bound:
                right_ctr.haptic([None, 1])

    def _wheel_update_common(self, angle, left_ctr, right_ctr):
        if angle:
            self._wheel_angles.append(angle)

        self.unwrap_wheel_angles()

        self.inertia()
        if (self._hand_snaps['left'][:5] != 'wheel') and (self._hand_snaps['right'][:5] != 'wheel'):
            self.center_force()
        self.limiter(left_ctr, right_ctr)
        self.send_to_vjoy()

    def ffb_haptic(self, left_ctr, right_ctr):

        # Consider both shifter and wheel for haptic
        left_bound = self._hand_snaps['left'] != ''
        right_bound = self._hand_snaps['right'] != ''

        # FFB haptic
        if self.config.wheel_ffb and \
            self.config.wheel_ffb_haptic and \
            self.ffb_paused == False:
            def compute_haptic_intensity(m_arr):

                window_size = 30
                m_arr = m_arr[:window_size]

                # Set thresholds for triggering haptics
                rms_threshold = 100 / 10000               # Minimum RMS value to consider

                # Calculate the first derivative of the magnitude array
                diffs = np.diff(m_arr)
                
                # Compute the RMS (root-mean-square) of the derivative
                rms_deriv = np.sqrt(np.mean(np.square(diffs)))
                
                if rms_deriv > rms_threshold:
                    rms_factor = min(2.0, rms_deriv / rms_threshold) / 2

                    # Scale intensity continuously based on both the RMS value and the composite factor.
                    pulse_intensity = rms_factor
                    return pulse_intensity
                return 0

            intensity = 0.5 * compute_haptic_intensity(self._center_speed_ffb_mags)
            if intensity > 0:
                def f(t, f):
                    if f%5 != 0:
                        return 0
                    return intensity
                if left_bound:
                    left_ctr.haptic([None, f])
                if right_bound:
                    right_ctr.haptic([None, f])

    def attach_hand(self, hand, left_ctr, right_ctr):
        left_ctr = self.to_wheel_space(left_ctr)
        right_ctr = self.to_wheel_space(right_ctr)

        ctr = left_ctr if hand == 'left' else right_ctr
        offset = [ctr.x - self.center.x, ctr.y - self.center.y]
        l = sqrt(offset[0]**2 + offset[1]**2)
        a = l/(self.size/2)

        """
        if l <= self._centerlimit_radius and self._snapped == False:
            # Put the hand in the center when it is not two-hand mode
            # if it is in the center of the wheel
            pass
        else:
        """
        offset[0] /= a
        offset[1] /= a
        
        tf = openvr.HmdMatrix34_t()
        for i in range(3):
            for j in range(3):
                tf[i][j] = self._rot[i][j]

        tf[0][3] = self.center.x + offset[0]
        tf[1][3] = self.center.y + offset[1] - self.hands_overlay.hand_z_offset
        tf[2][3] = self.center.z + 0.005

        ab = self.to_absolute_space(Point(tf[0][3], tf[1][3], tf[2][3]))

        tf[0][3] = ab.x
        tf[1][3] = ab.y
        tf[2][3] = ab.z
        self.hands_overlay.move(hand, tf)

    GRIP_FLAG_AUTO_GRAB = 0x1

    def _update_hands(self, grip_info, left_ctr, right_ctr):
        now = time.time()
        hand = grip_info[0]
        flag = 0 if len(grip_info) < 3 else grip_info[2]

        ctr = left_ctr if hand == 'left' else right_ctr
        grabber = self.hands_overlay.left_grab if hand == 'left' else self.hands_overlay.right_grab
        ungrabber = self.hands_overlay.left_ungrab if hand == 'left' else self.hands_overlay.right_ungrab
        other = 'left' if hand == 'right' else 'right'

        if grip_info[1] == False:
            v = self._hand_snaps[hand]
            self._hand_snaps[hand] = ''

            if v[:5] == 'wheel':
                self._snapped = False
            elif v == 'shifter':
                self.h_shifter_image.unsnap()

                def enabler():
                    # Enabling and disabling buttons and axes are to prevent scenario like those where
                    # the user ungrabs the shifter while ranging down (pushing the axis down),
                    # resulting in the input for the axis down gets registered since the user has ungrabbed the shifter;
                    # if the user has set up a key for axis down then the ranging down and the input get registered at the same time

                    # Enable splitter/range related buttons back
                    ## Wait for each button to be unpressed to prevent unwanted button presses
                    t = [False, False, False, True]
                    c = ctr

                    if self.config.trigger_pre_press_button:
                        # Also enable trigger touch if it is configured so
                        t[3] = False

                    while True:

                        self._shifter_button_lock.acquire()
                        if self._hand_snaps[hand] == 'shifter' or self._hand_snaps['right'] == 'shifter':
                            self._shifter_button_lock.release()
                            break

                        if t[0]:
                            pass
                        elif c.is_pressed(openvr.k_EButton_SteamVR_Trigger) == False:
                            self.enable_axis(hand, openvr.k_EButton_SteamVR_Trigger)
                            t[0] = True

                        if t[1]:
                            pass
                        elif c.is_pressed(openvr.k_EButton_A) == False:
                            self.enable_button(hand, openvr.k_EButton_A)
                            t[1] = True

                        if t[2]:
                            pass
                        elif abs(c.trackpadY) <= 0.1:
                            self.enable_axis(hand, 'down-up')
                            t[2] = True

                        if t[3]:
                            pass
                        elif c.is_touched(openvr.k_EButton_SteamVR_Trigger) == False:
                            self.enable_button(hand, 'trigger-touch')
                            t[3] = True
                        
                        self._shifter_button_lock.release()

                        if False not in t:
                            break

                        time.sleep(0.1)

                t = threading.Thread(target=enabler)
                t.start()

            self.hands_overlay.attach_to_ctr(hand)
            ungrabber()
        else:
            if self._hand_snaps[hand] == 'wheel_auto':
                self._hand_snaps[hand] = 'wheel'
                return
            if self._hand_snaps[hand] != '':
                return

            if self.check_colliding_object(ctr) == 'shifter' and (flag & self.GRIP_FLAG_AUTO_GRAB == 0):

                # Only one hand at a time
                if self._hand_snaps[other] == 'shifter':
                    return

                self._shifter_button_lock.acquire() # ACQUIRE ----------

                self._hand_snaps[hand] = 'shifter'

                # Disable splitter/range buttons so that it won't register
                
                self.disable_axis(hand, openvr.k_EButton_SteamVR_Trigger)
                self.disable_axis(hand, 'down-up')
                self.disable_button(hand, openvr.k_EButton_A)
                
                if self.config.trigger_pre_press_button:
                    # If user uses trigger touch, disable it also
                    self.disable_button(hand, 'trigger-touch')

                self._shifter_button_lock.release() # RELEASE ----------

                self.h_shifter_image.snap_ctr(ctr)
                ctr.haptic(*[(None, 0.5)]*3)
                #ctr.haptic([0.08, lambda t: min(1.0, 0.6 + math.exp(-8 * t))])
                #openvr.VRSystem().triggerHapticPulse(ctr.id, 0, 300)
            else:
                self._hand_snaps[hand] = 'wheel' if (flag & self.GRIP_FLAG_AUTO_GRAB == 0) else 'wheel_auto'
            
            grabber()

    def check_colliding_object(self, ctr):
        # Exact knob collision takes top priority
        if self.h_shifter_image.check_collision(ctr):
            return 'shifter'

        # Wheel takes 2nd priority
        margin = 0.075
        if (ctr.x < self.center.x + self.size / 2 + margin and
            ctr.x > self.center.x - self.size / 2 - margin):
            return 'wheel'

        return 'shifter'

    def update(self, left_ctr, right_ctr, hmd):
        super().update(left_ctr, right_ctr, hmd)

        now = time.time()

        # Hands
        if self.hands_overlay is None:
            self.hands_overlay = HandsImage(self.left_ctr, self.right_ctr)
            self.hands_overlay.closed_hands_always_top()

        # Check hands
        while not self._grip_queue.empty():
            self._update_hands(self._grip_queue.get(), left_ctr, right_ctr)

        # Check for automatic grabbing
        if self.config.wheel_grabbed_by_grip:
            pass
        else:
            lh = self.point_in_holding_bounds(left_ctr)
            rh = self.point_in_holding_bounds(right_ctr)

            if self._last_left_in_holding != lh:
                if lh:
                    self._grip_queue.put(['left', True, self.GRIP_FLAG_AUTO_GRAB])
                elif self._hand_snaps['left'] == 'wheel_auto':
                    self._grip_queue.put(['left', False])

            if self._last_right_in_holding != rh:
                if rh:
                    self._grip_queue.put(['right', True, self.GRIP_FLAG_AUTO_GRAB])
                elif self._hand_snaps['right'] == 'wheel_auto':
                    self._grip_queue.put(['right', False])

            if self.ready_to_unsnap(left_ctr, right_ctr):
                self._snapped = False

            self._last_left_in_holding = lh
            self._last_right_in_holding = rh

        # Update hand transform
        for i in self._hand_snaps.items():
            hand = i[0]
            obj = i[1]
            if obj == 'wheel':
                self.attach_hand(hand, left_ctr, right_ctr)
            elif obj == 'shifter':
                self.h_shifter_image.attach_hand(hand)
        perf_time("After update hands")

        # Wheel angle
        angle = self._wheel_update(left_ctr, right_ctr)
        self._wheel_update_common(angle, left_ctr, right_ctr)

        # FFB haptic
        self.ffb_haptic(left_ctr, right_ctr)

        # render
        self.render(hmd)
        perf_time("After self.render")
        self.h_shifter_image.render(hmd)
        perf_time("After self.h_shifter_image.render")
        self.h_shifter_image.update()
        perf_time("After self.h_shifter_image.update")

        # Up down joystick for Range
        shifter_hand = ''
        if self._hand_snaps['left'] == 'shifter':
            shifter_hand = 'left'
        if self._hand_snaps['right'] == 'shifter':
            shifter_hand = 'right'
        if shifter_hand != '':
            shifter_ctr = left_ctr if shifter_hand == 'left' else right_ctr
            y = shifter_ctr.trackpadY
            if y >= 0.8:
                self.h_shifter_image.toggle_range(shifter_ctr, True)
            elif y <= -0.8:
                self.h_shifter_image.toggle_range(shifter_ctr, False)

            trg = shifter_ctr.axis
            if trg >= 0.7:
                self.h_shifter_image.unlock_reverse()
            else:
                self.h_shifter_image.lock_reverse()

        perf_time("After shifter hands")

        # (ETS2)
        if True:
            # https://github.com/RenCloud/scs-sdk-plugin/blob/master/scs-client/C%23/SCSSdkClient/SCSSdkConvert.cs
            mm = mmap.mmap(0, 32*1024, "Local\\SCSTelemetry")

            a = struct.unpack("?", mm[0:1])[0] # sdk active
            p = struct.unpack("?", mm[4:5])[0] # paused
            d = struct.unpack("I", mm[64:68])[0] # time in minutes
            # NOTE you can get speed for getting G value for

            v = abs(((d%1440) / 60) - 13.5)
            
            cl = 1.0
            if a == False or p == True:
                pass
            else:
                min_cl = 0.035
                if v < 4.5:
                    pass
                elif v < 8:
                    cl = (1-min_cl) - ((v-4.5)/3.5)*(1-min_cl) + min_cl
                else:
                    cl = min_cl

            cmp_cl0 = round(cl * 255)
            cmp_cl1 = round(self._ets2_last_hand_cl * 255)
            if cmp_cl0 != cmp_cl1:
                self._ets2_last_hand_cl = cl

                self.wheel_image.set_color((cl,cl,cl))
                self.hands_overlay.set_color((cl,cl,cl))
                self.h_shifter_image.set_color((cl,cl,cl)) 
            
    def move_delta(self, d):
        self.center = Point(self.center.x + d[0], self.center.y + d[1], self.center.z + d[2])
        self.config.wheel_center = [self.center.x, self.center.y, self.center.z]
        self.wheel_image.move_rotate(pos=self.center, size=self.size)

    def resize_delta(self, d):
        if self.size + d < 0.10:
            return
        self.size += d
        self.config.wheel_size = self.size
        self.wheel_image.move_rotate(size=self.size)

    def pitch_delta(self, d):
        self.config.wheel_pitch += d
        self.config.wheel_pitch %= 360
        if self.config.wheel_pitch >= 330:
            self.config.wheel_pitch = max(-30, -(360 - self.config.wheel_pitch))
        elif self.config.wheel_pitch >= 120:
            self.config.wheel_pitch = 120
        self.config.wheel_pitch = round(self.config.wheel_pitch)

        self._rot = rotation_matrix(-self.config.wheel_pitch, 0, 0)
        self._rot_inv = rotation_matrix(self.config.wheel_pitch, 0, 0)
        self.wheel_image.move_rotate(pitch_roll=[
            self.config.wheel_pitch,
            self._wheel_angles[-1]/pi*180
            ])

    def discard_x(self):
        self.center = Point(0, self.center.y, self.center.z)
        self.config.wheel_center = [self.center.x, self.center.y, self.center.z]
        self.wheel_image.move_rotate(pos=self.center)

    def pre_edit_mode(self):
        super().pre_edit_mode()

        left_ctr = self.left_ctr
        right_ctr = self.right_ctr

        self._hand_snaps['left'] = ''
        self._hand_snaps['right'] = ''
        self.hands_overlay.attach_to_ctr('left')
        self.hands_overlay.attach_to_ctr('right')
        self.hands_overlay.left_ungrab()
        self.hands_overlay.right_ungrab()
        while not self._grip_queue.empty():
            self._grip_queue.get()

        self.enable_all()

        self._edit_snaps = {'left': '', 'right': ''}
        self._edit_buttons_frame = {'left': [0] * 64, 'right': [0] * 64}
        self._edit_discard_x = False
        self._edit_last_l_pos = [left_ctr.x, left_ctr.y, left_ctr.z]
        self._edit_last_r_pos = [right_ctr.x, right_ctr.y, right_ctr.z]
        self._edit_cl = {'wheel': None, 'shifter': None}
        self._edit_cl_override = {'wheel': None, 'shifter': None}
        self._edit_alpha = {'wheel': None, 'shifter': None}
        self._edit_alpha_override = {'wheel': None, 'shifter': None}
        self._edit_timers = {
            'wheel_alpha': None,
            'shifter_alpha': None,
            'shifter_xz': None
        }
        self._edit_shifter_xz = None
        
        if self.hands_overlay is not None:
            self.hands_overlay.show()
        if self.wheel_image is not None:
            self.wheel_image.show()

        print(_I("intro.wheel.edit_mode"))

    def post_edit_mode(self):
        super().post_edit_mode()

        for key in self._edit_timers:
            if self._edit_timers[key] is not None:
                self._edit_timers[key].cancel()
                self._edit_timers[key] = None

        self.wheel_image.set_alpha(self.config.wheel_alpha / 100.0)
        self.h_shifter_image.set_alpha(self.config.shifter_alpha / 100.0)

        self.wheel_image.set_color((1,1,1))
        self.h_shifter_image.set_color((1,1,1))
        self.hands_overlay.set_color((1,1,1))

    def edit_mode(self, frames):

        super().edit_mode(frames)

        def distance(p0, ctr):
            return sqrt((p0.x-ctr.x)**2 + (p0.y-ctr.y)**2 + (p0.z-ctr.z)**2)

        hmd = self.hmd
        left_ctr = self.left_ctr
        right_ctr = self.right_ctr
        now = time.time()

        cl_idle = (0, 0.5, 0)
        cl_collide = (0.5, 1, 0.4)
        cl_moviong = (1, 0.1, 0.1)

        if self._edit_shifter_xz is None:
            self.h_shifter_image.render(hmd)
        else:
            self.h_shifter_image.render(hmd, xz_override=self._edit_shifter_xz)

        _, state_l = openvr.VRSystem().getControllerState(left_ctr.id)
        _, state_r = openvr.VRSystem().getControllerState(right_ctr.id)
        dp_l = [left_ctr.x-self._edit_last_l_pos[0],
                left_ctr.y-self._edit_last_l_pos[1],
                left_ctr.z-self._edit_last_l_pos[2]]
        dp_r = [right_ctr.x-self._edit_last_r_pos[0],
                right_ctr.y-self._edit_last_r_pos[1],
                right_ctr.z-self._edit_last_r_pos[2]]
        params = [['left', dp_l, state_l, left_ctr],
                  ['right', dp_r, state_r, right_ctr]]

        if self._edit_snaps['left'] != 'wheel' and self._edit_snaps['right'] != 'wheel':
            self._edit_cl['wheel'] = cl_idle
            self._edit_alpha['wheel'] = 1
        if self._edit_snaps['left'] != 'shifter' and self._edit_snaps['right'] != 'shifter':
            self._edit_cl['shifter'] = cl_idle
            self._edit_alpha['shifter'] = 1

        for hand, dp, state, ctr in params:

            # EVRControllerAxisType
            #  k_eControllerAxis_None = 0, 
            #  k_eControllerAxis_TrackPad = 1,
            #  k_eControllerAxis_Joystick = 2,
            #  k_eControllerAxis_Trigger = 3, // Analog trigger data is in the X axis
            # rAxis
            x, y = [0, 0]
            if state.rAxis:
                x = state_r.rAxis[0].x # quest 2 joystick
                y = state_r.rAxis[0].y

            # Button frame
            buttons = [bit == '1' for bit in reversed(bin(state.ulButtonPressed)[2:])]
            buttons += [False] * (64 - len(buttons))
            def try_button(i):
                if buttons[i] and frames - self._edit_buttons_frame[hand][i] >= 12:
                    self._edit_buttons_frame[hand][i] = frames
                    return True
                return False

            # Collision
            snap = self._edit_snaps[hand]
            collide = ''
            if self.h_shifter_image.check_collision(ctr):
                collide = 'shifter'
            elif self.point_in_holding_bounds(ctr):
                collide = 'wheel'

            if snap == '' and collide != '':
                self._edit_cl[collide] = cl_collide

            # Snapping objects to hand
            if buttons[openvr.k_EButton_Grip]:
                if try_button(openvr.k_EButton_Grip):
                    if collide != '' and snap == 'ready':
                        self._edit_snaps[hand] = collide
                        self._edit_cl[collide] = cl_moviong

                        if collide == 'wheel':
                            # When snapping wheel
                            self._edit_discard_x = False

                    elif snap == '' and collide != '':
                        # Prevent object being grabbed while exiting the edit mode
                        self._edit_snaps[hand] = 'ready'
            else:
                
                self._edit_snaps[hand] = ''

            def adjust_alpha(obj_key, cfg_key):

                step = 10
                old_alpha = getattr(self.config, cfg_key)
                new_alpha = old_alpha + step
                if new_alpha > 100:
                    new_alpha = 0
                setattr(self.config, cfg_key, new_alpha)
                    
                self._edit_cl_override[obj_key] = (1, 1, 1)
                self._edit_alpha_override[obj_key] = new_alpha / 100.0

                # Timer
                def reset_preview():
                    self._edit_cl_override[obj_key] = None
                    self._edit_alpha_override[obj_key] = None

                old_timer = self._edit_timers[cfg_key]
                if old_timer is not None:
                    old_timer.cancel()

                new_timer = threading.Timer(1, reset_preview)
                new_timer.start()
                self._edit_timers[cfg_key] = new_timer

            # Edit object
            if snap == 'wheel':
                if self._edit_discard_x:
                    dp[0] = 0
                self.move_delta(dp)
            
            elif snap == 'shifter':
                self.h_shifter_image.move_delta(dp)

            if (snap == '' or snap == 'wheel') and collide == 'wheel':

                self.resize_delta(dead_and_stretch(x, 0.3) / 240)
                self.pitch_delta(dead_and_stretch(y, 0.75) * 2)

                if try_button(openvr.k_EButton_ApplicationMenu):
                   adjust_alpha('wheel', 'wheel_alpha')

                if try_button(openvr.k_EButton_A):
                    self._edit_discard_x = not self._edit_discard_x
                    if self._edit_discard_x:
                        self.discard_x()

            elif (snap == '' or snap == 'shifter') and collide == 'shifter':

                if try_button(openvr.k_EButton_ApplicationMenu):
                   adjust_alpha('shifter', 'shifter_alpha')

                if try_button(openvr.k_EButton_A):
                    self.h_shifter_image.toggle_sequential()

                tilt_delta = dead_and_stretch(x, 0.3) / 2
                if tilt_delta != 0.0:
                    self.h_shifter_image.tilt_delta(tilt_delta)
                    self.config.shifter_degree = int(self.h_shifter_image.degree * 10)

                    if self._edit_timers['shifter_xz'] is not None:
                        self._edit_timers['shifter_xz'].cancel()

                    def reset_preview():
                        self._edit_shifter_xz = None
                    self._edit_shifter_xz = [1,1]
                    self._edit_timers['shifter_xz'] = threading.Timer(0.6, reset_preview)
                    self._edit_timers['shifter_xz'].start()

                scale_delta = dead_and_stretch(y, 0.5) / 100
                if scale_delta != 0.0:
                    self.h_shifter_image.rescale_delta(scale_delta)
                    self.config.shifter_scale = int(self.h_shifter_image.stick_scale * 100)

        self._edit_last_l_pos = [left_ctr.x, left_ctr.y, left_ctr.z]
        self._edit_last_r_pos = [right_ctr.x, right_ctr.y, right_ctr.z]

        # Color and alpha
        def get_first(*args):
            for a in args:
                if a is not None:
                    return a
        self.wheel_image.set_alpha(get_first(self._edit_alpha_override['wheel'], self._edit_alpha['wheel']))
        self.wheel_image.set_color(get_first(self._edit_cl_override['wheel'], self._edit_cl['wheel']))
        self.h_shifter_image.set_alpha(get_first(self._edit_alpha_override['shifter'], self._edit_alpha['shifter']))
        self.h_shifter_image.set_color(get_first(self._edit_cl_override['shifter'], self._edit_cl['shifter']))
