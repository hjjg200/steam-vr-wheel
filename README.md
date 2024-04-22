# steam-vr-wheel

This fork is a version I modified for personal use only. So it is highly likely that it won't work on other platforms than Quest 2 or alike. If you're, by any chance, inclined to try, download from the releases, since the current commit could be unfunctional.

## Memo

Qyuest 2 vJoy mapping

|Key|Button ID|Note|
|-|-|-|
|LT|1||
|LT Touch|31||
|L Grip|2|Disabled|
|LS|4,5,6,7,8||
|RT|9||
|RT Touch|32||
|R Grip|10|Disabled|
|RS|12,13,14,15,16||
|A|18||
|B|11||
|X|17||
|Y|3||

### Todo

- Make wheel and shifter rotatable in space; wheel around x axis; shifter all 3 axes
- Clean up unused configs
- Code cleanup

### Config memo

Memos for \*original\* config behaviors. Some configs' behaviors are changed as I don't have Vive controllers to test the behavior

|Config|Module|Behavior|
|-|-|-|
|Triggers pre press button|`VirtualPad`|Touching trigger registers|
|Triggers press button|`VirtualPad`|Trigger press registers along with axis change|
|5 Button touchpad|`VirtualPad`|On Quest 2 controller, the axis values determine button id|
|Haptic feedback for trackpad button zones|`VirtualPad`|Haptic when 5-button button id changed|
|Touchpad mapping to axis while untouched (axis move to center when released)|`VirtualPad`||
|Steering wheel is vertical|`Wheel`||
|Joystick moves only when grabbed (by right grip)|`Joystick`||
|Joystick grab is a switch|`Joystick`||
|Layout edit mode|`Wheel`||
|Manual wheel grabbing|`Wheel`||
|Continuous (index, checked) or toggle (vive) wheel gripping|`Wheel`||
|Show Wheel Overlay|`Wheel`||
|Show Hands Overlay|`Wheel`||

Changed(applied or planned) behavior:

|Config|Behavior|
|-|-|
|Triggers pre press button|Set default to disabled|
|Triggers press button||
|5 Button touchpad|Disabled as default, more description|
|Haptic feedback for trackpad button zones|Disabled as default, more description|
|Touchpad mapping to axis while untouched (axis move to center when released)|Disabled, since joysticks are handlded differently now|
|Steering wheel is vertical|Disabled, the wheel will be manually rotatable in edit mode|
|Joystick moves only when grabbed (by right grip)|Hidden; use the original version for better experience|
|Joystick grab is a switch|Hidden|
|Layout edit mode|Disabled, users have to enter edit mode by triple grip clicks|
|Manual wheel grabbing||
|Continuous (index, checked) or toggle (vive) wheel gripping||
|Show Wheel Overlay||
|Show Hands Overlay||

## This fork

### Comaptibility

- Compatibility of devices other than Quest 2 is not tested.
- Only the wheel mode(wheel.bat) is tested.

### Edit Mode

Triple grip clicks of both the left and right controllers trigger the edit mode.

Move your RIGHT controller to the center of the wheel and press the trigger on RIGHT controller; while holding down:
- Resize: Move RIGHT joystick up and down to resize the wheel.
- Transparency: Press B button to cycle through the transparency mode.
- Align Center: Press A button to align the wheel to center.

Move your RIGHT controller to the knob of the shifter to adjust its position.

Pressing the grip on RIGHT exits the edit mode.

### Quest 2's Joystick to Buttons

You can convert all direcitons of the joysticks to buttons or leave it as axis.

Example 1, if you choose to convert the Left Joy Down to button, Left Joy Left and Left Joy Right will remain as the same axis; the Left Joy Up will be solely adjusting the axis while the Left Joy Down acts as a button.

Example 2, you can make all 8 directions to buttons; so that you can use them like dpads.

|Joystick|Axis|Button ID|
|-|-|-|
|L Left|Z Axis|34|
|L Right|Z Axis|35|
|L Down|Y|36|
|L Up|Y|37|
|R Left|RX|38|
|R Right|RX|39|
|R Down|RY|40|
|R Up|RY|41|

### Virtual H Shifter

```text
<Video Demo>
```

It is a h-shifter with 6 positions, a splitter(A while grabbing knob), and a range selector(Trigger while grabbing knob).

```text
1 3 5
2 4 6
```
|Key|Button ID|Note|
|-|-|-|
|Position 1|43||
|Position 2|44||
|Position 3|45||
|Position 4|46||
|Position 5|47||
|Position 6|48||
|Neutral|42||
|Splitter|49|Grab knob and A|
|Range Selector|50|Grab knob and Trigger|
