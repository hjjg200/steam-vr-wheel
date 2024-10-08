import os
import random
import threading
import time

import openvr
import sys

main_done = False

def wheel_main_done():
    global main_done
    return main_done

from steam_vr_wheel._bike import Bike
from steam_vr_wheel._virtualpad import VirtualPad
from steam_vr_wheel._wheel import Wheel
from steam_vr_wheel.vrcontroller import Controller
from steam_vr_wheel.configurator import run

FREQUENCY = 60

if 'DEBUG' in sys.argv:
    DEBUG = True
    FREQUENCY = 1
else:
    DEBUG = False



def get_chaperone():

    vrchp_setup = openvr.VRChaperoneSetup()
    _, chp = vrchp_setup.getWorkingSeatedZeroPoseToRawTrackingPose()

    return chp

def do_work(vrsystem, left_controller: Controller, right_controller: Controller, hmd: Controller, wheel: Wheel, poses):
    vrsystem.getDeviceToAbsoluteTrackingPose(openvr.TrackingUniverseSeated, 0, len(poses), poses)
    hmd.update(poses[hmd.id.value])
    left_controller.update(poses[left_controller.id.value])
    right_controller.update(poses[right_controller.id.value])
    event = openvr.VREvent_t()
    while vrsystem.pollNextEvent(event):
        hand = None

        if event.eventType == openvr.VREvent_ChaperoneUniverseHasChanged:
            wheel.update_chaperone(get_chaperone())

            # no pitch and roll
            # https://github.com/ValveSoftware/openvr/issues/905

            #vrchp_setup.function_table.setWorkingSeatedZeroPoseToRawTrackingPose(byref(chp))
            #vrchp_setup.commitWorkingCopy(openvr.EChaperoneConfigFile_Live)

        if event.trackedDeviceIndex == left_controller.id.value:

            if event.eventType == openvr.VREvent_ButtonTouch:
                if DEBUG:
                    print("LEFT HAND EVENT: BUTTON TOUCH, BUTTON ID", event.data.controller.button)
                if event.data.controller.button == openvr.k_EButton_SteamVR_Touchpad:
                    wheel.set_trackpad_touch_left()
                elif  event.data.controller.button == openvr.k_EButton_SteamVR_Trigger:
                    wheel.set_trigger_touch_left()
            elif  event.eventType == openvr.VREvent_ButtonUntouch:
                if DEBUG:
                    print("LEFT HAND EVENT: BUTTON UNTOUCH, BUTTON ID", event.data.controller.button)
                if event.data.controller.button == openvr.k_EButton_SteamVR_Touchpad:
                    wheel.set_trackpad_untouch_left()
                elif  event.data.controller.button == openvr.k_EButton_SteamVR_Trigger:
                    wheel.set_trigger_untouch_left()

            hand = 'left'
        if event.trackedDeviceIndex == right_controller.id.value:

            if event.eventType == openvr.VREvent_ButtonTouch:
                if DEBUG:
                    print("RIGHT HAND EVENT: BUTTON TOUCH, BUTTON ID", event.data.controller.button)
                if event.data.controller.button == openvr.k_EButton_SteamVR_Touchpad:
                    wheel.set_trackpad_touch_right()
                elif  event.data.controller.button == openvr.k_EButton_SteamVR_Trigger:
                    wheel.set_trigger_touch_right()
            elif  event.eventType == openvr.VREvent_ButtonUntouch:
                if DEBUG:
                    print("RIGHT HAND EVENT: BUTTON UNTOUCH, BUTTON ID", event.data.controller.button)

                if event.data.controller.button == openvr.k_EButton_SteamVR_Touchpad:
                    wheel.set_trackpad_untouch_right()
                elif  event.data.controller.button == openvr.k_EButton_SteamVR_Trigger:
                    wheel.set_trigger_untouch_right()

            hand = 'right'
        if hand:
            if event.eventType == openvr.VREvent_ButtonPress:
                if DEBUG:
                    print(hand, "HAND EVENT: BUTTON PRESS, BUTTON ID", event.data.controller.button)
                button = event.data.controller.button
                wheel.set_button_press(button, hand, left_controller, right_controller)
            if event.eventType == openvr.VREvent_ButtonUnpress:
                if DEBUG:
                    print(hand, "HAND EVENT: BUTTON UNPRESS, BUTTON ID", event.data.controller.button)
                button = event.data.controller.button
                wheel.set_button_unpress(button, hand)
    if wheel.is_edit_mode:
        wheel.edit_mode(left_controller, right_controller, hmd)
    else:
        wheel.update(left_controller, right_controller, hmd)


def get_controller_ids():
    vrsys = openvr.VRSystem()
    for i in range(openvr.k_unMaxTrackedDeviceCount):
        device_class = vrsys.getTrackedDeviceClass(i)
        if device_class == openvr.TrackedDeviceClass_Controller:
            role = vrsys.getControllerRoleForTrackedDeviceIndex(i)
            if role == openvr.TrackedControllerRole_RightHand:
                 right = i
            if role == openvr.TrackedControllerRole_LeftHand:
                 left = i

        elif device_class == openvr.TrackedDeviceClass_HMD:
            hmd = i
    return hmd, left, right


def main(type='wheel'):
    openvr.init(openvr.VRApplication_Overlay)
    vrsystem = openvr.VRSystem()
    hands_got = False

    while not hands_got:
        try:
            print('Searching for left and right hand controllers')
            hmd, left, right = get_controller_ids()
            hands_got = True
            print('left and right hands found')
        except NameError:
            pass
        time.sleep(0.2)

    hmd_device = Controller(hmd, name='hmd', vrsys=vrsystem, is_controller=False)
    left_controller = Controller(left, name='left', vrsys=vrsystem)
    right_controller = Controller(right, name='right', vrsys=vrsystem)
    if type == 'wheel':
        wheel = Wheel()
    elif type == 'bike':
        wheel = Bike()
    elif type == 'pad':
        wheel = VirtualPad()

    # Pre loop
    wheel.update_chaperone(get_chaperone())

    poses_t = openvr.TrackedDevicePose_t * openvr.k_unMaxTrackedDeviceCount
    poses = poses_t()

    # Loop
    while True:
        before_work = time.time()
        do_work(vrsystem, left_controller, right_controller, hmd_device, wheel, poses)
        after_work = time.time()
        left = 1/FREQUENCY - (after_work - before_work)
        if left>0:
            time.sleep(left)
        else:
            print("Task took too long +", -left, "seconds")

if __name__ == '__main__':
    try:
        main()
    except:
        main_done = True
