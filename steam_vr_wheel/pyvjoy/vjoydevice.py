
from .constants import *
from .exceptions import *

import steam_vr_wheel.pyvjoy._sdk as _sdk


class VJoyDevice(object):
	"""Object-oriented API for a vJoy Device"""

	def __init__(self,rID=None, data=None):
		"""Constructor"""

		self.rID=rID
		self._sdk= _sdk
		self._vj=self._sdk._vj
		
		if data:
			self.data = data
		else:
			#TODO maybe - have self.data as a wrapper object containing the Struct
			self.data = self._sdk.CreateDataStructure(self.rID)

		try:
			_sdk.vJoyEnabled()
			_sdk.AcquireVJD(rID)

		#TODO FIXME
		except vJoyException:
			raise

			
	def set_button(self,buttonID,state):
		"""Set a given button (numbered from 1) to On (1 or True) or Off (0 or False)"""
		return self._sdk.SetBtn(state,self.rID,buttonID)

		
	def set_axis(self,AxisID, AxisValue):
		"""Set a given Axis (one of pyvjoy.HID_USAGE_X etc) to a value (0x0000 - 0x8000)"""
		return self._sdk.SetAxis(AxisValue,self.rID,AxisID)
		
		
	def reset(self):
		"""Reset all axes and buttons to default values"""
			
		return self._sdk.ResetVJD(self.rID)

		
	def reset_data(self):
		"""Reset the data Struct to default (does not change vJoy device at all directly)"""
		self.data=self._sdk.CreateDataStructure(self.rID)
			
		
	def reset_buttons(self):
		"""Reset all buttons on the vJoy Device to default"""
		return self._sdk.ResetButtons(self.rID)

		
	def reset_povs(self):
		"""Reset all Povs on the vJoy Device to default"""
		return self._sdk.ResetPovs(self.rID)

		
	def update(self):
		"""Send the stored Joystick data to the device in one go (the 'efficient' method)"""
		return self._sdk.UpdateVJD(self.rID, self.data)

	# FFB
	def is_device_ffb(self):
		return self._sdk.IsDeviceFfb(self.rID)

	def ffb_callback(self, cb):
		def wrapped(data):
			if not "DeviceID" in data:
				return
			if data["DeviceID"] != self.rID:
				return
			cb(data)
		self._cb = wrapped
		self._ffb_gen_cb = self._sdk.FfbRegisterGenCB(self._cb) # func(dict)

	
