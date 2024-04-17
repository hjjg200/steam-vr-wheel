import sys
import wx

from steam_vr_wheel import PadConfig, ConfigException

class ConfiguratorApp:
    def __init__(self):

        self.app = wx.App()
        self.window = wx.Frame(None, title="Steam Vr Wheel Configuration")
        self.pnl = wx.Panel(self.window)
        self.vbox = wx.BoxSizer(wx.VERTICAL)
        self.trigger_pre_btn_box = wx.CheckBox(self.pnl, label='Triggers pre press button')
        self.trigger_btn_box = wx.CheckBox(self.pnl, label='Triggers press button')
        self.multibutton_trackpad_box = wx.CheckBox(self.pnl, label='5 Button touchpad')
        self.multibutton_trackpad_center_haptic_box = wx.CheckBox(self.pnl,
                                                                  label='Haptic feedback for trackpad button zones')
        self.touchpad_always_updates_box = wx.CheckBox(self.pnl, label='Touchpad mapping to axis while untouched (axis move to center when released)')
        self.vertical_wheel_box = wx.CheckBox(self.pnl, label='Steering wheel is vertical')
        self.joystick_updates_only_when_grabbed_box = wx.CheckBox(self.pnl, label='Joystick moves only when grabbed (by right grip)')
        self.joystick_grabbing_switch_box = wx.CheckBox(self.pnl, label='Joystick grab is a switch')
        self.edit_mode_box = wx.CheckBox(self.pnl, label='Layout edit mode')
        self.wheel_grabbed_by_grip_box = wx.CheckBox(self.pnl, label='Manual wheel grabbing')
        self.wheel_grabbed_by_grip_box_toggle = wx.CheckBox(self.pnl, label='Continuous (index, checked) or toggle (vive) wheel gripping')
        self.wheel_show_wheel = wx.CheckBox(self.pnl, label="Show Wheel Overlay")
        self.wheel_show_hands = wx.CheckBox(self.pnl, label="Show Hands Overlay")
        self.wheel_degrees = wx.SpinCtrl(self.pnl, name = "Wheel Degrees", max = 10000)
        self.wheel_centerforce = wx.SpinCtrl(self.pnl, name = "Center Force")
        self.wheel_alpha = wx.SpinCtrl(self.pnl, name = "Wheel Alpha", max = 100)

        # Shifter
        self.shifter_degree = wx.SpinCtrl(self.pnl, name = "Shifter Degree, 15deg", min=0, max=90)
        self.shifter_alpha = wx.SpinCtrl(self.pnl, name = "Shifter Alpha (%), 100%", min=0, max=100)
        self.shifter_size = wx.SpinCtrl(self.pnl, name = "Shifter Size (cm), 7cm", min=1, max=100)

        # Joystick button or axis
        self.pnl_joystick = wx.Panel(self.window)
        self.hbox_joystick = wx.BoxSizer(wx.HORIZONTAL)
        self.j_l_left_button = wx.CheckBox(self.pnl_joystick, label='L ◀')
        self.j_l_right_button = wx.CheckBox(self.pnl_joystick, label='L ▶')
        self.j_l_up_button = wx.CheckBox(self.pnl_joystick, label='L ▲')
        self.j_l_down_button = wx.CheckBox(self.pnl_joystick, label='L ▼')
        self.j_r_left_button = wx.CheckBox(self.pnl_joystick, label='R ◀')
        self.j_r_right_button = wx.CheckBox(self.pnl_joystick, label='R ▶')
        self.j_r_up_button = wx.CheckBox(self.pnl_joystick, label='R ▲')
        self.j_r_down_button = wx.CheckBox(self.pnl_joystick, label='R ▼')


        self.trigger_pre_btn_box.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.trigger_btn_box.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.multibutton_trackpad_box.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.multibutton_trackpad_center_haptic_box.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.touchpad_always_updates_box.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.vertical_wheel_box.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.joystick_updates_only_when_grabbed_box.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.joystick_grabbing_switch_box.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.edit_mode_box.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.wheel_grabbed_by_grip_box.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.wheel_grabbed_by_grip_box_toggle.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.wheel_show_wheel.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.wheel_show_hands.Bind(wx.EVT_CHECKBOX, self.config_change)
        self.wheel_degrees.Bind(wx.EVT_SPINCTRL, self.config_change)
        self.wheel_centerforce.Bind(wx.EVT_SPINCTRL, self.config_change)
        self.wheel_alpha.Bind(wx.EVT_SPINCTRL, self.config_change)

        # Shifter
        self.shifter_degree.Bind(wx.EVT_SPINCTRL, self.config_change)
        self.shifter_alpha.Bind(wx.EVT_SPINCTRL, self.config_change)
        self.shifter_size.Bind(wx.EVT_SPINCTRL, self.config_change)

        self._config_map = dict(trigger_pre_press_button=self.trigger_pre_btn_box,
                                trigger_press_button=self.trigger_btn_box,
                                multibutton_trackpad=self.multibutton_trackpad_box,
                                multibutton_trackpad_center_haptic=self.multibutton_trackpad_center_haptic_box,
                                touchpad_always_updates=self.touchpad_always_updates_box,
                                vertical_wheel=self.vertical_wheel_box,
                                joystick_updates_only_when_grabbed=self.joystick_updates_only_when_grabbed_box,
                                joystick_grabbing_switch=self.joystick_grabbing_switch_box,
                                edit_mode=self.edit_mode_box,
                                wheel_grabbed_by_grip=self.wheel_grabbed_by_grip_box,
                                wheel_grabbed_by_grip_toggle=self.wheel_grabbed_by_grip_box_toggle,
                                wheel_show_wheel=self.wheel_show_wheel,
                                wheel_show_hands=self.wheel_show_hands,
                                wheel_degrees=self.wheel_degrees,
                                wheel_centerforce=self.wheel_centerforce,
                                wheel_alpha=self.wheel_alpha,

                                shifter_degree=self.shifter_degree,
                                shifter_alpha=self.shifter_alpha,
                                shifter_size=self.shifter_size,
                                )

        self.vbox.Add(self.trigger_pre_btn_box)
        self.vbox.Add(self.trigger_btn_box)
        self.vbox.Add(self.multibutton_trackpad_box)
        self.vbox.Add(self.multibutton_trackpad_center_haptic_box)
        self.vbox.Add(self.touchpad_always_updates_box)
        self.vbox.Add(self.vertical_wheel_box)
        self.vbox.Add(self.joystick_updates_only_when_grabbed_box)
        self.vbox.Add(self.joystick_grabbing_switch_box)
        self.vbox.Add(self.edit_mode_box)
        self.vbox.Add(self.wheel_grabbed_by_grip_box)
        self.vbox.Add(self.wheel_grabbed_by_grip_box_toggle)
        self.vbox.Add(self.wheel_show_wheel)
        self.vbox.Add(self.wheel_show_hands)
        self.vbox.AddSpacer(10)
        self.vbox.Add(wx.StaticText(self.pnl, label = "Wheel Degrees"))
        self.vbox.Add(self.wheel_degrees)
        self.vbox.AddSpacer(4)
        self.vbox.Add(wx.StaticText(self.pnl, label = "Wheel Center Force"))
        self.vbox.Add(self.wheel_centerforce)
        self.vbox.AddSpacer(4)
        self.vbox.Add(wx.StaticText(self.pnl, label = "Wheel Alpha"))
        self.vbox.Add(self.wheel_alpha)

        self.vbox.AddSpacer(10)
        self.vbox.Add(wx.StaticText(self.pnl, label = "Shifter Alpha"))
        self.vbox.Add(self.shifter_alpha)
        self.vbox.AddSpacer(4)
        self.vbox.Add(wx.StaticText(self.pnl, label = "Shifter Degree"))
        self.vbox.Add(self.shifter_degree)
        self.vbox.AddSpacer(4)
        self.vbox.Add(wx.StaticText(self.pnl, label = "Shifter Size"))
        self.vbox.Add(self.shifter_size)

        self.vbox.AddSpacer(10)
        self.vbox.Add(wx.StaticText(self.pnl, label = "Use Joystick as Axis/Button"))
        self.vbox.Add(wx.StaticText(self.pnl, label = "- Checked joystick acts as button"))
        self.hbox_joystick.Add(self.j_l_left_button)
        self.hbox_joystick.Add(self.j_l_right_button)
        self.hbox_joystick.Add(self.j_l_up_button)
        self.hbox_joystick.Add(self.j_l_down_button)
        self.hbox_joystick.Add(self.j_r_left_button)
        self.hbox_joystick.Add(self.j_r_right_button)
        self.hbox_joystick.Add(self.j_r_up_button)
        self.hbox_joystick.Add(self.j_r_down_button)
        self.pnl_joystick.SetSizerAndFit(self.hbox_joystick)
        self.vbox.Add(self.pnl_joystick)

        self.pnl.SetSizerAndFit(self.vbox)
        self.read_config()
        self.window.Fit()
        self.window.Show(True)

    def read_config(self):
        try:
            self.config = PadConfig()
        except ConfigException as e:
            msg = "Config error: {}. Load defaults?".format(e)
            dlg = wx.MessageDialog(self.pnl, msg, "Config Error", wx.YES_NO | wx.ICON_QUESTION)
            result = dlg.ShowModal() == wx.ID_YES
            dlg.Destroy()
            if result:
                self.config = PadConfig(load_defaults=True)
            else:
                sys.exit(1)
        for key, item in self._config_map.items():
            item.SetValue(getattr(self.config, key))

    def config_change(self, event):
        for key, item in self._config_map.items():
            setattr(self.config, key, item.GetValue())

    def run(self):
        self.app.MainLoop()


def run():
    ConfiguratorApp().run()

if __name__ == '__main__':
    run()