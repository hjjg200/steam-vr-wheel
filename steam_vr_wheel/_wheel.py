from collections import deque
from math import pi, atan2, sin, cos, ceil, sqrt, acos, tan

import numpy as np
import openvr
import os
import copy
import time
import threading
import queue

from . import check_result, rotation_matrix, playsound
from steam_vr_wheel._virtualpad import VirtualPad
from steam_vr_wheel.pyvjoy import HID_USAGE_X, FFB_CTRL, FFBPType, FFBOP

def print_matrix(matrix):
    l = []
    for i in range(3):
        ll = []
        for j in range(4):
            ll.append(matrix[j])
        l.append(ll)
    print(l)

def rotation_matrix_around_vec(theta, vec):
    theta = theta * np.pi / 180
    m = sqrt(vec[0]**2 + vec[1]**2 + vec[2]**2)
    ux = vec[0]/m
    uy = vec[1]/m
    uz = vec[2]/m
    s, c = sin(theta), cos(theta)

    return np.array([[c+ux**2*(1-c), ux*uy*(1-c)-uz*s, ux*uz*(1-c)+uy*s],
                    [uy*ux*(1-c)+uz*s, c+uy**2*(1-c), uy*uz*(1-c)-ux*s],
                    [uz*ux*(1-c)-uy*s, uz*uy*(1-c)+ux*s, c+uz**2*(1-c)]])

def initRotationMatrix(axis, angle, matrix=None):
    # angle in radians
    if matrix is None:
        matrix = openvr.HmdMatrix34_t()
    if axis==0:
        matrix.m[0][0] = 1.0
        matrix.m[0][1] = 0.0
        matrix.m[0][2] = 0.0
        matrix.m[0][3] = 0.0
        matrix.m[1][0] = 0.0
        matrix.m[1][1] = cos(angle)
        matrix.m[1][2] = -sin(angle)
        matrix.m[1][3] = 0.0
        matrix.m[2][0] = 0.0
        matrix.m[2][1] = sin(angle)
        matrix.m[2][2] = cos(angle)
        matrix.m[2][3] = 0.0
    elif axis==1:
        matrix.m[0][0] = cos(angle)
        matrix.m[0][1] = 0.0
        matrix.m[0][2] = sin(angle)
        matrix.m[0][3] = 0.0
        matrix.m[1][0] = 0.0
        matrix.m[1][1] = 1.0
        matrix.m[1][2] = 0.0
        matrix.m[1][3] = 0.0
        matrix.m[2][0] = -sin(angle)
        matrix.m[2][1] = 0.0
        matrix.m[2][2] = cos(angle)
        matrix.m[2][3] = 0.0
    elif axis == 2:
        matrix.m[0][0] = cos(angle)
        matrix.m[0][1] = -sin(angle)
        matrix.m[0][2] = 0.0
        matrix.m[0][3] = 0.0
        matrix.m[1][0] = sin(angle)
        matrix.m[1][1] = cos(angle)
        matrix.m[1][2] = 0.0
        matrix.m[1][3] = 0.0
        matrix.m[2][0] = 0.0
        matrix.m[2][1] = 0.0
        matrix.m[2][2] = 1.0
        matrix.m[2][3] = 0.0
    return matrix


def matMul33(a, b, result=None):
    if result is None:
        result = openvr.HmdMatrix34_t()
    for i in range(3):
        for j in range(3):
            result.m[i][j] = 0.0
            for k in range(3):
                result.m[i][j] += a.m[i][k] * b.m[k][j]
    result[0][3] = b[0][3]
    result[1][3] = b[1][3]
    result[2][3] = b[2][3]
    return result



class HShifterImage:
    def __init__(self, wheel, x=0.25, y=-0.57, z=-0.15, degree=15, scale=100, alpha=100):
        self.vrsys = openvr.VRSystem()
        self.vroverlay = openvr.IVROverlay()

        self.x = x
        self.y = y
        self.z = z
        self.size = 14 / 100
        self.degree = degree
        self.pos = 3.5
        self.wheel = wheel

        #self._button_queue = []
        self._snap_ctr = None
        self._snap_start_pos = False
        self._snapped = False
        self._snap_times = []
        self._snap_db_timer = None
        self._snap_ctr_offset = []
        self._snap_tf = None

        self._knob_pos = [0,0,0]

        self._splitter_toggled = False
        self._range_toggled = False
        self._reverse_locked = True

        self._pos_to_button = dict({-1: 51,     1: 43,     3: 45,     5: 47,     7: 51,
                                    -0.5: None, 1.5: None, 3.5: None, 5.5: None, 7.5: None,
                                    0: 51,      2: 44,     4: 46,     6: 48,     8: 51})
        self._pressed_button = None
        self._xz = [0,0]
        self._last_xz_grid = np.array([0,0])

        # Create
        result, self.slot = self.vroverlay.createOverlay('hshifter_slot'.encode(), 'hshifter_slot'.encode())
        check_result(result)
        result, self.stick = self.vroverlay.createOverlay('hshifter_stick'.encode(), 'hshifter_stick'.encode())
        check_result(result)
        result, self.knob = self.vroverlay.createOverlay('hshifter_knob'.encode(), 'hshifter_knob'.encode())
        check_result(result)

        # Media
        this_dir = os.path.abspath(os.path.dirname(__file__))

        # Sound
        self._change_mp3_1 = os.path.join(this_dir, 'media', 'shifter_change_1.mp3')
        self._change_mp3_2 = os.path.join(this_dir, 'media', 'shifter_change_2.mp3')
        self._last_change_play = 0

        # Images
        slot_img = os.path.join(this_dir, 'media', 'h_shifter_slot_7.png')
        self._stick_img = os.path.join(this_dir, 'media', 'h_shifter_stick_low.png')
        self._stick_img_2 = os.path.join(this_dir, 'media', 'h_shifter_stick_high.png')
        self._knob_img = os.path.join(this_dir, 'media', 'h_shifter_knob.png')
        self._knob_img_2 = os.path.join(this_dir, 'media', 'h_shifter_knob_over.png')

        check_result(self.vroverlay.setOverlayFromFile(self.slot, slot_img.encode()))
        check_result(self.vroverlay.setOverlayFromFile(self.stick, self._stick_img.encode()))
        check_result(self.vroverlay.setOverlayFromFile(self.knob, self._knob_img.encode()))

        # Visibility
        check_result(self.vroverlay.setOverlayColor(self.slot, 0.2, 0.2, 0.2)) # default gray outline
        check_result(self.vroverlay.setOverlayAlpha(self.slot, alpha/100))
        check_result(self.vroverlay.setOverlayWidthInMeters(self.slot, self.size)) # default 14cm
        
        stick_width = 0.02
        self.stick_width = stick_width
        txw, txh = 40, 633
        stick_height = txh / (txw / stick_width)
        stick_scale = scale / 100 # 1.0 => 31.65cm
        stick_height *= stick_scale
        check_result(self.vroverlay.setOverlayColor(self.stick, 1, 1, 1))
        check_result(self.vroverlay.setOverlayAlpha(self.stick, alpha/100))
        check_result(self.vroverlay.setOverlayWidthInMeters(self.stick, stick_width))

        check_result(self.vroverlay.setOverlayColor(self.knob, 1, 1, 1))
        check_result(self.vroverlay.setOverlayAlpha(self.knob, alpha/100))
        check_result(self.vroverlay.setOverlayWidthInMeters(self.knob, 0.05))

        def set_transform(tf, mat):
            for i in range(0, 3):
                for j in range(0, 4):
                    tf[i][j] = mat[i][j]

        # Position
        ## Slot
        result, self.slot_tf = self.vroverlay.setOverlayTransformAbsolute(self.slot, openvr.TrackingUniverseSeated)
        check_result(result)
        result, self.slot_uv = self.vroverlay.getOverlayTextureBounds(self.slot)
        check_result(result)
        set_transform(self.slot_tf, [[1.0, 0.0, 0.0, x],
                                    [0.0, 0.0, 1.0, y],
                                    [0.0, -1.0, 0.0, z]]) # 90deg at X

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

        ## Stick
        result, self.stick_tf = self.vroverlay.setOverlayTransformAbsolute(self.stick, openvr.TrackingUniverseSeated)
        check_result(result)
        result, self.stick_uv = self.vroverlay.getOverlayTextureBounds(self.stick)
        check_result(result)
        set_transform(self.stick_tf, [[1.0, 0.0, 0.0, x],
                                    [0.0, stick_scale, 0.0, y+stick_height/2],
                                    [0.0, 0.0, 1.0, z]])
        self.stick_uv.vMax = stick_scale
        self.stick_height = stick_height
        self.stick_scale = stick_scale
        check_result(self.vroverlay.function_table.setOverlayTextureBounds(self.stick, openvr.byref(self.stick_uv)))

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

        self.last_pos = 3.5

    def check_collision(self, ctr):
        if self.wheel.config.shifter_adaptive_bounds:
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
        else:
            x, y, z = ctr.x, ctr.y, ctr.z
            pm, pM = self.bounds
            x0, y0, z0 = pm
            x2, y2, z2 = pM
            
            return x0<=x<=x2 and y0<=y<=y2 and z0<=z<=z2

    def set_stick_xz_pos(self, xz_pos, ctr=None):
        
        """
        |1  |3  |5  |  43 45 47
        |1.5|3.5|5.5|     42
        |2  |4  |6  |  44 46 48

        double tap 49  triple tap 50
        """
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

    def toggle_splitter(self, ctr):
        self._splitter_toggled = not self._splitter_toggled
        check_result(self.vroverlay.setOverlayFromFile(self.knob, 
            self._knob_img_2.encode() if self._splitter_toggled else self._knob_img.encode()))

        def haptic():
            openvr.VRSystem().triggerHapticPulse(ctr.id, 0, 3000)
            time.sleep(0.11)
            openvr.VRSystem().triggerHapticPulse(ctr.id, 0, 3000)
        t = threading.Thread(target=haptic)
        t.start()

    def toggle_range(self, ctr, override=None):
        if override is not None:
            if self._range_toggled == override:
                return
            
            self._range_toggled = override
        else:
            self._range_toggled = not self._range_toggled
        
        check_result(self.vroverlay.setOverlayFromFile(self.stick,
            self._stick_img_2.encode() if self._range_toggled else self._stick_img.encode()))

        def haptic():
            openvr.VRSystem().triggerHapticPulse(ctr.id, 0, 3000)
            time.sleep(0.11)
            openvr.VRSystem().triggerHapticPulse(ctr.id, 0, 3000)
        t = threading.Thread(target=haptic)
        t.start()

    def snap_ctr(self, ctr):
        now = time.time()
        self._snap_ctr = ctr
        self._snap_ctr_offset = [ctr.x - self._knob_pos[0], ctr.y - self._knob_pos[1], ctr.z - self._knob_pos[2]]
        self._snapped = True

    def unsnap(self):
        self._snapped = False
        if self._pressed_button is None:
            self.set_stick_xz_pos([0,0])

        self._move_stick(self._xz_pos())

        """
        |1  |3  |5  |  1 3 5
        |1.5|3.5|5.5|  +-N-+
        |2  |4  |6  |  2 4 6

        odd: towards -z
        x2 is odd: no rotation
        even: towards +z

        x = (round(pos/2)-1) * ...
        z_rot = ((pos%2 if pos%2 != 0 else 2)-1.5) * ...
        """

    def _xz_pos(self):
        return [(ceil(self.pos/2)-2), ((self.pos%2 if self.pos%2 != 0 else 2)-1.5)*2]

    def _move_stick(self, xz):
        self._xz = xz

    def render(self, hmd):
        # xz = relative and normalized
        xz = self._xz

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
        if self.wheel.config.shifter_adaptive_bounds:
            self.collision_radius = 0.07
        else:
            x_sin_full = sin(self.degree*pi/180) * self.stick_height
            z_sin_full = sin(self.degree*pi/180) * self.stick_height
            margin = 0.05

            if self._xz_rev[0] == -2:
                self.bounds = [
                    [self.x - (x_sin_full+unit)*2 - margin, y_knob+0.1-0.15, self.z -z_sin_full-unit - margin], 
                    [self.x + x_sin_full+unit     + margin, y_knob+0.1     , self.z +z_sin_full+unit + margin]]
            else:
                self.bounds = [
                    [self.x - x_sin_full-unit     - margin, y_knob+0.1-0.15, self.z -z_sin_full-unit - margin], 
                    [self.x + (x_sin_full+unit)*2 + margin, y_knob+0.1     , self.z +z_sin_full+unit + margin]]

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

    def move_delta(self, d):
        self.x += d[0]
        self.y += d[1]
        self.z += d[2]
        self.wheel.config.shifter_center = [self.x, self.y, self.z]

    def update(self):

        for v in self._pos_to_button.values():
            if v != self._pressed_button and v is not None:
                self.wheel.device.set_button(v, False)
        if self._pressed_button is not None:
            self.wheel.device.set_button(self._pressed_button, True)

        now = time.time()

        # Toggles
        self.wheel.device.set_button(49, self._splitter_toggled)
        self.wheel.device.set_button(50, self._range_toggled)

        if self._snapped:
            u_sin = (self.stick_height * sin(self.degree*pi/180))
            unit = (self.size/4 - self.stick_width/2)

            ctr = self._snap_ctr
            p1 = [ctr.x, ctr.y, ctr.z]
            p1[0] -= self._snap_ctr_offset[0]
            #p1[1] -= self._snap_ctr_offset[1]
            p1[2] -= self._snap_ctr_offset[2]

            dp_unsafe = (p1[0]-self.x, 0, p1[2]-self.z)
            dp_unsafe = [dp_unsafe[0] / (u_sin + unit),
                        0,
                        dp_unsafe[2] / (u_sin + unit)]

            if self._xz_rev[0] == -2:
                xz_ctr = np.array([
                    max(min(dp_unsafe[0], 1.0), -2.0),
                    max(min(dp_unsafe[2], 1.0), -1.0)])
            else:
                xz_ctr = np.array([
                    max(min(dp_unsafe[0], 2.0), -1.0),
                    max(min(dp_unsafe[2], 1.0), -1.0)])

            xz_rev_z_clamper = max if self._xz_rev[1] == 1 else min

            x_mid_margin = 0.55
            z_end_margin = 0.85
            z_mid_margin = 0.7

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
                            xz_pos_1[1] = 0
                    else:
                        if xz_ctr[1] < -z_end_margin:
                            xz_pos_1[1] = -1
                        else:
                            xz_pos_1[1] = 0

                else:
                    xz_1[1] = xz_ctr[1]
                    if xz_ctr[1] < -z_end_margin:
                        xz_pos_1[1] = -1
                    elif xz_ctr[1] > z_end_margin:
                        xz_pos_1[1] = 1
                    else:
                        xz_pos_1[1] = 0

            restrained_margin = 1.5
            if abs(dp_unsafe[0]-xz_pos_1[0]) > restrained_margin or abs(dp_unsafe[2]-xz_pos_1[1]) > restrained_margin:
                openvr.VRSystem().triggerHapticPulse(ctr.id, 0, 1500)

            if xz_pos_0 != xz_pos_1 and xz_pos_1[1] != 0:
                # Gear change
                openvr.VRSystem().triggerHapticPulse(ctr.id, 0, 3000)

                if now - self._last_change_play > 0.07:
                    #p = multiprocessing.Process(target=player)
                    # If ever block issue, use multiprocessing
                    def player():
                        # TODO maybe add volume to configurator
                        playsound(self._change_mp3_2 if xz_pos_1[1] == -1 else self._change_mp3_1,
                            block=False, volume=0.65)
                    t = threading.Thread(target=player)
                    t.start()
                    self._last_change_play = now

            self._move_stick(xz_1)
            self.set_stick_xz_pos(xz_pos_1)


class SteeringWheelImage:
    def __init__(self, x=0, y=-0.4, z=-0.35, size=0.55, alpha=1):
        self.vrsys = openvr.VRSystem()
        self.vroverlay = openvr.IVROverlay()
        result, self.wheel = self.vroverlay.createOverlay('keyiiii'.encode(), 'keyiiii'.encode())
        check_result(result)

        check_result(self.vroverlay.setOverlayColor(self.wheel, 1, 1, 1))
        check_result(self.vroverlay.setOverlayAlpha(self.wheel, alpha))
        check_result(self.vroverlay.setOverlayWidthInMeters(self.wheel, size))

        this_dir = os.path.abspath(os.path.dirname(__file__))
        wheel_img = os.path.join(this_dir, 'media', 'steering_wheel.png')

        check_result(self.vroverlay.setOverlayFromFile(self.wheel, wheel_img.encode()))


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



class Point:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

class GrabControllerPoint(Point):
    def __init__(self, x, y, z, id=0):
        super().__init__(x, y, z)
        self.id = id


class Wheel(VirtualPad):
    def __init__(self, inertia=0.95, center_speed=pi/180):
        super().__init__()
        self.vrsys = openvr.VRSystem()
        self.hands_overlay = None
        self.is_edit_mode = False
        x, y, z = self.config.wheel_center
        size = self.config.wheel_size
        self._inertia = inertia
        self._center_speed = center_speed  # radians per frame, force which returns wheel to center when not grabbed
        self._center_speed_ffb = 0 
        # FFB
        if self.config.wheel_ffb:
            self.device.ffb_callback(self.ffb_callback)
            self._ffb_stopped = False
            self._ffb_end = 0

        self.x = 0  # -1 0 1
        self._wheel_angles = deque(maxlen=10)
        self._wheel_angles.append(0)
        self._wheel_angles.append(0)
        self._snapped = False

        self._rot = rotation_matrix(-self.config.wheel_pitch, 0, 0)
        self._rot_inv = rotation_matrix(self.config.wheel_pitch, 0, 0)

        # Adaptive wheel centering
        self._wheel_adpative_offset = [0, 0]

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
        self._last_knob_haptic = 0
        self._shifter_button_lock = threading.Lock()

    def ffb_callback(self, data):

        now = time.time()
        if hasattr(self, "_ffb_test_t") == False:
            self._ffb_test_t = now - 20.0
            self._ffb_test_unhandled = dict()
            self._ffb_test_handled = dict()

            self.last_now = now
            self._ffb_test_dir_map = dict()

        def _ffb_test_f(handled, t, sub=None):
            k = str(t)
            if sub is not None:
                k += "-" + str(sub)

            d = self._ffb_test_handled if handled else self._ffb_test_unhandled
            if not k in d:
                d[k] = 0
            d[k] += 1

        elapsed = now-self.last_now

        # Ignored types
        typ = data['Type']
        if typ in [
            FFBPType.PT_CONDREP, # Ignore condtions
            ]:
            _ffb_test_f(True, typ)

        # Gain
        if typ == FFBPType.PT_GAINREP:
            _ffb_test_f(False, typ)

        #FFBPType.PT_EFOPREP 10
        if "EffOp" in data:
            op = data['EffOp']['EffectOp']
            if op == FFBOP.EFF_START or op == FFBOP.EFF_SOLO:

                self._ffb_stopped = False
            
                loop = data['EffOp']['LoopCount']
                if loop == 0:
                    # Indefinite loop
                    _ffb_test_f(True, FFBPType.PT_EFOPREP, op)
                else:
                    # Not handled
                    _ffb_test_f(False, FFBPType.PT_EFOPREP, "%d-%d" % (op, loop))

            elif op == FFBOP.EFF_STOP:
                self._ffb_stopped = True
                _ffb_test_f(True, FFBPType.PT_EFOPREP, op)
            else:
                # Not handled
                _ffb_test_f(False, FFBPType.PT_EFOPREP, op)

        #FFBPType.PT_EFFREP
        if "Eff_Report" in data:

            rep = data["Eff_Report"]
            d = rep["Duration"]
            if d == 0xFFFF:
                self._ffb_end = now + 86400 * 365
            else:
                self._ffb_end = now + d/1000.0

            # Dir map
            self._ffb_test_dir_map["DirX %d" % rep["DirX"]] = 0
            self._ffb_test_dir_map["Direction %d" % rep["Direction"]] = 0

            _ffb_test_f(True, FFBPType.PT_EFFREP)

        #FFBPType.PT_CONSTREP
        if "Eff_Constant" in data:
            self._center_speed_ffb = data['Eff_Constant']['Magnitude'] / 10000.0
            if elapsed != 0:
                self._center_speed_ffb *= elapsed * 200

            _ffb_test_f(True, FFBPType.PT_CONSTREP)
        
        #FFBPType.PT_PRIDREP
        if "Eff_Period" in data:
            _ffb_test_f(False, FFBPType.PT_PRIDREP)

        #FFBPType.PT_CTRLREP
        if "DevCtrl" in data:
            if data['DevCtrl'] in [FFB_CTRL.CTRL_STOPALL, FFB_CTRL.CTRL_DEVRST]:
                self._center_speed_ffb = 0
                _ffb_test_f(True, FFBPType.PT_CTRLREP, data['DevCtrl'])
            else:
                _ffb_test_f(False, FFBPType.PT_CTRLREP, data['DevCtrl'])

        if typ not in [
            FFBPType.PT_CONSTREP,
            FFBPType.PT_CTRLREP,
            FFBPType.PT_EFOPREP,
            FFBPType.PT_CONDREP,
            FFBPType.PT_PRIDREP,
            FFBPType.PT_EFFREP,
            FFBPType.PT_GAINREP,

            # [TEST] FFB behaviors
            # NO  {'13': 2, '11': 1, '10-1-1': 4, '17': 4}
            # YES {'13': 2, '5': 74874, '1': 4, '12-4': 3, '10-3': 2, '12-3': 14, '3': 10060}
            # Dir {'DirX 0': 0, 'Direction 0': 0}

            # 17, 11, 1

            ]:
            _ffb_test_f(False, typ)

        if now - self._ffb_test_t > 30.0:
            print("[TEST] FFB behaviors",
                "\n  NO ", self._ffb_test_unhandled,
                "\n  YES", self._ffb_test_handled,
                "\n  Dir", self._ffb_test_dir_map)
            self._ffb_test_t = now

        self.last_now = now


    def point_in_holding_bounds(self, point):
        point = self.to_wheel_space(point)

        a = self.size/2 + 0.06
        b = self.size/2 - 0.10

        adapt_center = Point(self.center.x+self._wheel_adpative_offset[0],
            self.center.y+self._wheel_adpative_offset[1],
            self.center.z)

        x = point.x - adapt_center.x
        y = point.y - adapt_center.y
        z = point.z - adapt_center.z

        if abs(z) < 0.075:
            distance = sqrt(x**2+y**2)
            if distance < b:
                return False
            if distance < a:
                return True
        else:
            return False

    def _subtract_and_rotate(self, point, mat):

        adapt_center = Point(self.center.x+self._wheel_adpative_offset[0],
            self.center.y+self._wheel_adpative_offset[1],
            self.center.z)

        diff = np.array([point.x-adapt_center.x,
                        point.y-adapt_center.y,
                        point.z-adapt_center.z])
        l = np.dot(mat, diff)
        l[0] += adapt_center.x
        l[1] += adapt_center.y
        l[2] += adapt_center.z
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

        adapt_center = Point(self.center.x+self._wheel_adpative_offset[0],
            self.center.y+self._wheel_adpative_offset[1],
            self.center.z)

        point = self.to_wheel_space(point)
        a = float(point.y) - adapt_center.y
        b = float(point.x) - adapt_center.x

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

        adapt_center = Point(self.center.x+self._wheel_adpative_offset[0],
            self.center.y+self._wheel_adpative_offset[1],
            self.center.z)

        dc = ((adapt_center.x - (l.x+r.x)/2)**2
              + (adapt_center.y - (l.y+r.y)/2)**2
              + (adapt_center.z - (l.z+r.z)/2)**2
              )
        if dc > self.size**2:
            return True

        return False

    def set_button_unpress(self, button, hand):
        super().set_button_unpress(button, hand)

        if self.config.wheel_grabbed_by_grip_toggle:
            if button == openvr.k_EButton_Grip and hand == 'left':
                self._grip_queue.put(['left', False])

            if button == openvr.k_EButton_Grip and hand == 'right':
                self._grip_queue.put(['right', False])
        else:
            pass

    def set_button_press(self, button, hand, left_ctr, right_ctr):
        ctr = left_ctr if hand == 'left' else right_ctr
        super().set_button_press(button, hand, left_ctr, right_ctr)

        if self._hand_snaps[hand] == 'shifter':
            if button == openvr.k_EButton_A: # A
                self.h_shifter_image.toggle_splitter(ctr)

        if button == openvr.k_EButton_Grip and hand == 'left':
            if self.config.wheel_grabbed_by_grip_toggle:
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

        if self._snapped:
            angle = self.wheel_double_raw_angle(left_ctr, right_ctr) + self._wheel_grab_offset
            return angle

        if right_bound:
            controller = right_ctr
            self.is_held(controller)
        elif left_bound:
            controller = left_ctr
            self.is_held(controller)
        else:
            self.is_not_held()
            return None
        angle = self.wheel_raw_angle(controller) + self._wheel_grab_offset
        return angle

    def calculate_grab_offset(self, raw_angle=None):
        if raw_angle is None:
            raw_angle = self.wheel_raw_angle(self._grab_started_point)
        self._wheel_grab_offset = self._wheel_angles[-1] - raw_angle

    def is_held(self, controller):

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
        self._grab_started_point = None

    def inertia(self):
        if self._grab_started_point:
            self._turn_speed = self._wheel_angles[-1] - self._wheel_angles[-2]
        else:
            self._wheel_angles.append(self._wheel_angles[-1] + self._turn_speed)
            self._turn_speed *= self._inertia

    def center_force(self):
        
        now = time.time()
        epsilon = self._center_speed * self.config.wheel_centerforce

        if self.config.wheel_ffb:

            if self._ffb_stopped or now > self._ffb_end:
                epsilon = 0
            else:
                epsilon *= self._center_speed_ffb

            self._wheel_angles.append(self._wheel_angles[-1] + epsilon)

        else:
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
        self.device.set_axis(HID_USAGE_X, axisX)

    def render(self, hmd):

        adapt_center = Point(self.center.x+self._wheel_adpative_offset[0],
            self.center.y+self._wheel_adpative_offset[1],
            self.center.z)

        self.wheel_image.move_rotate(
            pos=adapt_center,
            pitch_roll=[
            self.config.wheel_pitch,
            self._wheel_angles[-1]/pi*180
            ])

        alpha = self.config.wheel_alpha / 100.0

        d = sqrt((adapt_center.x-hmd.x)**2+
                    (adapt_center.y-hmd.y)**2+
                    (adapt_center.z-hmd.z)**2)
        p2 = hmd.normal.copy() * d
        pc_d = sqrt((adapt_center.x-p2[0])**2+
                    (adapt_center.y-p2[1])**2+
                    (adapt_center.z-p2[2])**2)
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

        if (self._hand_snaps['left'][:5] != 'wheel' and
            self._hand_snaps['right'][:5] != 'wheel'):
            self.reset_adapt_center()

        self.wheel_image.set_alpha(alpha)

    def limiter(self, left_ctr, right_ctr):
        if abs(self._wheel_angles[-1])/(2*pi)>(self.config.wheel_degrees / 360)/2:
            self._wheel_angles[-1] = self._wheel_angles[-2]

            sign = 1
            if self._wheel_angles[-1] < 0:
                sign = -1
            self._turn_speed = -0.005 * sign

            openvr.VRSystem().triggerHapticPulse(left_ctr.id, 0, 3000)
            openvr.VRSystem().triggerHapticPulse(right_ctr.id, 0, 3000)

    def _wheel_update_common(self, angle, left_ctr, right_ctr):
        if angle:
            self._wheel_angles.append(angle)

        self.unwrap_wheel_angles()

        self.inertia()
        if (self._hand_snaps['left'][:5] != 'wheel') and (self._hand_snaps['right'][:5] != 'wheel'):
            self.center_force()
        self.limiter(left_ctr, right_ctr)
        self.send_to_vjoy()

    def attach_hand(self, hand, left_ctr, right_ctr):
        left_ctr = self.to_wheel_space(left_ctr)
        right_ctr = self.to_wheel_space(right_ctr)

        adapt_center = Point(self.center.x+self._wheel_adpative_offset[0],
            self.center.y+self._wheel_adpative_offset[1],
            self.center.z)

        ctr = left_ctr if hand == 'left' else right_ctr
        offset = [ctr.x - adapt_center.x, ctr.y - adapt_center.y]
        a = sqrt(offset[0]**2 + offset[1]**2)/(self.size/2)
        offset[0] /= a
        offset[1] /= a
        tf = openvr.HmdMatrix34_t()
        for i in range(3):
            for j in range(3):
                tf[i][j] = self._rot[i][j]

        tf[0][3] = adapt_center.x + offset[0]
        tf[1][3] = adapt_center.y + offset[1] - self.hands_overlay.hand_z_offset
        tf[2][3] = adapt_center.z + 0.005

        ab = self.to_absolute_space(Point(tf[0][3], tf[1][3], tf[2][3]))

        tf[0][3] = ab.x
        tf[1][3] = ab.y
        tf[2][3] = ab.z
        self.hands_overlay.move(hand, tf)

    def pre_edit_mode(self):
        super().pre_edit_mode()

        self._hand_snaps['left'] = ''
        self._hand_snaps['right'] = ''
        self.hands_overlay.attach_to_ctr('left')
        self.hands_overlay.attach_to_ctr('right')
        self.hands_overlay.left_ungrab()
        self.hands_overlay.right_ungrab()
        while not self._grip_queue.empty():
            self._grip_queue.get()

        self.enable_all()

    GRIP_FLAG_AUTO_GRAB = 0x1

    def _update_hands(self, grip_info, left_ctr, right_ctr):
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
                    # Enable splitter/range related buttons back
                    ## Wait for each button to be unpressed to prevent unwanted button presses
                    t = [False, False, False, False]
                    c = ctr
                    while True:

                        self._shifter_button_lock.acquire()
                        if self._hand_snaps['left'] == 'shifter' or self._hand_snaps['right'] == 'shifter':
                            self._shifter_button_lock.release()
                            break

                        if t[0]:
                            pass
                        elif c.is_pressed(openvr.k_EButton_SteamVR_Trigger) == False:
                            self.enable_button(hand, openvr.k_EButton_SteamVR_Trigger)
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
                        elif c.axis <= 0.1:
                            self.enable_axis(hand, 'trigger')
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

            grabber()
            if self.h_shifter_image.check_collision(ctr) and (flag & self.GRIP_FLAG_AUTO_GRAB == 0):

                self._shifter_button_lock.acquire()
                self._hand_snaps[hand] = 'shifter'

                # Disable splitter/range buttons so that it won't register
                self.disable_button(hand, openvr.k_EButton_SteamVR_Trigger)
                self.disable_axis(hand, 'trigger')
                self.disable_button(hand, openvr.k_EButton_A)
                self.disable_axis(hand, 'down-up')
                self._shifter_button_lock.release()

                self.h_shifter_image.snap_ctr(ctr)

                openvr.VRSystem().triggerHapticPulse(ctr.id, 0, 300)
            else:
                self._hand_snaps[hand] = 'wheel' if (flag & self.GRIP_FLAG_AUTO_GRAB == 0) else 'wheel_auto'

    def adapt_center(self, left_ctr, right_ctr):
        limit_radius = 0.045
        ctr = None
        if self._hand_snaps['left'][:5] == 'wheel':
            ctr = left_ctr
        if self._hand_snaps['right'][:5] == 'wheel':
            if ctr is not None:
                return
            ctr = right_ctr

        if ctr is None:
            return

        adapt_center = Point(self.center.x+self._wheel_adpative_offset[0],
            self.center.y+self._wheel_adpative_offset[1],
            self.center.z)

        ctr_wheel = self.to_wheel_space(ctr)
        l = sqrt((adapt_center.x-ctr_wheel.x)**2+
                (adapt_center.y-ctr_wheel.y)**2)

        if l < limit_radius:
            off = [ctr_wheel.x-adapt_center.x, ctr_wheel.y-adapt_center.y]
            c = (limit_radius-l) / l
            off[0] *= c
            off[1] *= c
            self._wheel_adpative_offset[0] -= off[0]
            self._wheel_adpative_offset[1] -= off[1]

    def reset_adapt_center(self):
        self._wheel_adpative_offset = [0, 0]

    def update(self, left_ctr, right_ctr, hmd):
        super().update(left_ctr, right_ctr, hmd)

        now = time.time()

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

        # Wheel angle
        if self.config.wheel_adaptive_center:
            self.adapt_center(left_ctr, right_ctr)
        angle = self._wheel_update(left_ctr, right_ctr)

        self._wheel_update_common(angle, left_ctr, right_ctr)

        self.render(hmd)
        self.h_shifter_image.render(hmd)
        self.h_shifter_image.update()

        # Slight haptic when touching knob
        if self._hand_snaps['left'] != 'shifter' and self._hand_snaps['right'] != 'shifter':
            if now - self._last_knob_haptic > 0.12:
                self._last_knob_haptic = now
                if self._hand_snaps['left'] == '' and self.h_shifter_image.check_collision(left_ctr):
                    openvr.VRSystem().triggerHapticPulse(left_ctr.id, 0, 100)
                if self._hand_snaps['right'] == '' and self.h_shifter_image.check_collision(right_ctr):
                    openvr.VRSystem().triggerHapticPulse(right_ctr.id, 0, 100)

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

    def edit_mode(self, left_ctr, right_ctr, hmd):

        result, state_r = openvr.VRSystem().getControllerState(right_ctr.id)
        now = time.time()

        if hasattr(self, "_edit_check") == False:
            self._edit_check = True
            self._edit_move_wheel = False
            self._edit_move_shifter = False
            self._edit_last_l_pos = [left_ctr.x, left_ctr.y, left_ctr.z]
            self._edit_last_r_pos = [right_ctr.x, right_ctr.y, right_ctr.z]
            self._edit_last_trigger_press = 0
            self._edit_wheel_alpha_timer = None

            self.wheel_image.set_alpha(1)

        if self.hands_overlay != None:
            self.hands_overlay.show()
        if self.wheel_image != None:
            self.wheel_image.show()

        self.h_shifter_image.render(hmd)

        r_d = [right_ctr.x-self._edit_last_r_pos[0], right_ctr.y-self._edit_last_r_pos[1], right_ctr.z-self._edit_last_r_pos[2]]

        if self._edit_move_wheel:
            #self.move_wheel(right_ctr, left_ctr)
            self.move_delta(r_d)
            self.wheel_image.set_color((1,0,0))
        else:
            self.wheel_image.set_color((0,1,0))

        if self._edit_move_shifter:
            self.h_shifter_image.move_delta(r_d)
            self.h_shifter_image.set_color((1,0,0))
        else:
            self.h_shifter_image.set_color((0,1,0))

        def distance(p0):
            return sqrt((p0.x-right_ctr.x)**2 + (p0.y-right_ctr.y)**2 + (p0.z-right_ctr.z)**2)

        # Todo: switch alpha, shows the alpha-applied wheel for a second and after that set alpha to 1

        # EVRControllerAxisType
        #  k_eControllerAxis_None = 0, 
        #  k_eControllerAxis_TrackPad = 1,
        #  k_eControllerAxis_Joystick = 2,
        #  k_eControllerAxis_Trigger = 3, // Analog trigger data is in the X axis
        # rAxis
        if state_r.rAxis:
            x = state_r.rAxis[0].x # quest 2 joystick
            y = state_r.rAxis[0].y
            if self._edit_move_wheel:
                def dead_and_stretch(v, d):
                    if abs(v) < d:
                        return 0.0
                    else:
                        s = v / abs(v)
                        return (v - s*d)/(1-d)
                self.resize_delta(dead_and_stretch(x, 0.3) / 240)
                self.pitch_delta(dead_and_stretch(y, 0.75) * 2)

        if state_r.ulButtonPressed:
            btns = list(reversed(bin(state_r.ulButtonPressed)[2:]))
            btn_id = btns.index('1')
            if btn_id == openvr.k_EButton_SteamVR_Trigger:
                if now - self._edit_last_trigger_press > 0.2:
                    if self.h_shifter_image.check_collision(right_ctr) and self._edit_move_wheel == False:
                        self._edit_move_shifter = True
                    elif distance(self.center) < 0.3 and self._edit_move_shifter == False:
                        self._edit_move_wheel = True
                self._edit_last_trigger_press = now
            elif btn_id == openvr.k_EButton_ApplicationMenu and now - self._edit_mode_last_press > 0.2: #B on right
                self._edit_mode_last_press = now
                step = 10
                if self.config.wheel_alpha + step > 100:
                    self.config.wheel_alpha = 0
                else:
                    self.config.wheel_alpha += step

                if self._edit_wheel_alpha_timer != None:
                    self._edit_wheel_alpha_timer.cancel()
                    self._edit_wheel_alpha_timer = None

                def reset_preview():
                    self.wheel_image.set_alpha(1)
                self._edit_wheel_alpha_timer = threading.Timer(0.6, reset_preview)
                self._edit_wheel_alpha_timer.start()

                print("Switch alpha")
                # Switch alpha and show preview
                self.wheel_image.set_alpha(self.config.wheel_alpha / 100.0)
            elif btn_id == openvr.k_EButton_A: #A on right
                self.discard_x()
                print("Set x to 0")
            elif btn_id == openvr.k_EButton_Grip and now - self._edit_mode_entry > 0.5:
                self.wheel_image.set_color((1,1,1))
                self.h_shifter_image.set_color((1,1,1))
                self.config.wheel_pitch = int(self.config.wheel_pitch)
                self.is_edit_mode = False
                self.__dict__.pop("_edit_check", None)
        else:
            if self._edit_move_wheel:
                self._edit_move_wheel = False
            if self._edit_move_shifter:
                self._edit_move_shifter = False

        self._edit_last_l_pos = [left_ctr.x, left_ctr.y, left_ctr.z]
        self._edit_last_r_pos = [right_ctr.x, right_ctr.y, right_ctr.z]
        super().edit_mode(left_ctr, right_ctr, hmd)
