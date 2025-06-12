#_aisound.py
#A part of NVDA AiSound 5 Synthesizer Add-On

import os
import weakref
import audioDucking
import NVDAHelper
from ctypes import *
from ctypes.wintypes import HANDLE, WORD, DWORD, UINT, LPUINT
from logHandler import log
from synthDriverHandler import synthIndexReached,synthDoneSpeaking

wrapperDLL=None
lastIndex=None
isPlaying=False
synthRef=None

aisound_callback_t=CFUNCTYPE(None,c_int,c_void_p)
SPEECH_BEGIN=0
SPEECH_END=1


HWAVEOUT = HANDLE
LPHWAVEOUT = POINTER(HWAVEOUT)


class WAVEFORMATEX(Structure):
	_fields_ = [
		("wFormatTag", WORD),
		("nChannels", WORD),
		("nSamplesPerSec", DWORD),
		("nAvgBytesPerSec", DWORD),
		("nBlockAlign", WORD),
		("wBitsPerSample", WORD),
		("cbSize", WORD),
	]


LPWAVEFORMATEX = POINTER(WAVEFORMATEX)

# Set argument types.
windll.winmm.waveOutOpen.argtypes = (
	LPHWAVEOUT,
	UINT,
	LPWAVEFORMATEX,
	DWORD,
	DWORD,
	DWORD
)
windll.winmm.waveOutGetID.argtypes = (HWAVEOUT, LPUINT)


class FunctionHooker(object):

	def __init__(
		self,
		targetDll: str,
		importDll: str,
		funcName: str,
		newFunction # result of ctypes.WINFUNCTYPE
	):
		# dllImportTableHooks_hookSingle expects byte strings.
		try:
			self._hook=NVDAHelper.localLib.dllImportTableHooks_hookSingle(
				targetDll.encode("mbcs"),
				importDll.encode("mbcs"),
				funcName.encode("mbcs"),
				newFunction
			)
		except UnicodeEncodeError:
			log.error("Error encoding FunctionHooker input parameters", exc_info=True)
			self._hook = None
		if self._hook:
			log.debug(f"Hooked {funcName}")
		else:
			log.error(f"Could not hook {funcName}")
			raise RuntimeError(f"Could not hook {funcName}")

	def __del__(self):
		if self._hook:
			NVDAHelper.localLib.dllImportTableHooks_unhookSingle(self._hook)

_duckersByHandle={}

@WINFUNCTYPE(windll.winmm.waveOutOpen.restype,*windll.winmm.waveOutOpen.argtypes,use_errno=False,use_last_error=False)
def waveOutOpen(pWaveOutHandle,deviceID,wfx,callback,callbackInstance,flags):
	try:
		res=windll.winmm.waveOutOpen(pWaveOutHandle,deviceID,wfx,callback,callbackInstance,flags) or 0
	except WindowsError as e:
		res=e.winerror
	if res==0 and pWaveOutHandle:
		h=pWaveOutHandle.contents.value
		d=audioDucking.AudioDucker()
		d.enable()
		_duckersByHandle[h]=d
	return res

@WINFUNCTYPE(c_long,c_long)
def waveOutClose(waveOutHandle):
	try:
		res=windll.winmm.waveOutClose(waveOutHandle) or 0
	except WindowsError as e:
		res=e.winerror
	if res==0 and waveOutHandle:
		_duckersByHandle.pop(waveOutHandle,None)
	return res

_waveOutHooks=[]
def ensureWaveOutHooks(dllPath):
	if not _waveOutHooks and audioDucking.isAudioDuckingSupported():
		_waveOutHooks.append(FunctionHooker(dllPath,"WINMM.dll","waveOutOpen",waveOutOpen))
		_waveOutHooks.append(FunctionHooker(dllPath,"WINMM.dll","waveOutClose",waveOutClose))


@aisound_callback_t
def callback(type,cbData):
	global lastIndex,isPlaying,synthRef
	if type==SPEECH_BEGIN:
		if cbData==None:
			lastIndex=0
		else:
			lastIndex=cbData
			synthIndexReached.notify(synth=synthRef(),index=lastIndex)
	elif type==SPEECH_END:
		isPlaying=False
		synthDoneSpeaking.notify(synth=synthRef())

def Initialize(synth: weakref.ReferenceType):
	global wrapperDLL,isPlaying,synthRef
	synthRef = synth
	if wrapperDLL==None:
		dllPath=os.path.abspath(os.path.join(os.path.dirname(__file__), r"aisound.dll"))
		ensureWaveOutHooks(dllPath)
		wrapperDLL=cdll.LoadLibrary(dllPath)
		wrapperDLL.aisound_callback.restype=c_bool
		wrapperDLL.aisound_callback.argtypes=[aisound_callback_t]
		wrapperDLL.aisound_configure.restype=c_bool
		wrapperDLL.aisound_configure.argtypes=[c_char_p,c_char_p]
		wrapperDLL.aisound_speak.restype=c_bool
		wrapperDLL.aisound_speak.argtypes=[c_char_p,c_void_p]
		wrapperDLL.aisound_cancel.restype=c_bool
		wrapperDLL.aisound_pause.restype=c_bool
		wrapperDLL.aisound_resume.restype=c_bool
	wrapperDLL.aisound_initialize()
	wrapperDLL.aisound_callback(callback)

def Terminate():
	global wrapperDLL
	wrapperDLL.aisound_terminate()

def Configure(name,value):
	global wrapperDLL
	return wrapperDLL.aisound_configure(name.encode("utf-8"),value.encode("utf-8"))

def Speak(text,index=None):
	global wrapperDLL,isPlaying
	if index==None:
		cbData=0
	else:
		cbData=index
	isPlaying=True
	return wrapperDLL.aisound_speak(text.encode("utf-8"),c_void_p(cbData))

def Cancel():
	global wrapperDLL,isPlaying,synthRef
	isPlaying=False
	synthDoneSpeaking.notify(synth=synthRef())
	return wrapperDLL.aisound_cancel()

def Pause():
	global wrapperDLL
	return wrapperDLL.aisound_pause()

def Resume():
	global wrapperDLL
	return wrapperDLL.aisound_resume()


# vim: set tabstop=4 shiftwidth=4 wm=0:
