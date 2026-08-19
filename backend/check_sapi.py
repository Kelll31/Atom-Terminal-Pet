import win32com.client
strm = win32com.client.Dispatch('SAPI.SpMemoryStream')
for i in range(1, 50):
    try:
        strm.Format.Type = i
        wf = strm.Format.GetWaveFormatEx()
        if wf and wf.SamplesPerSec == 16000 and wf.BitsPerSample == 16 and wf.Channels == 1:
            print(f'Type {i} is 16kHz 16-bit Mono!')
    except:
        pass
