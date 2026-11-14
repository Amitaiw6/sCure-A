# Synthesizes a soft ambient bed (60 s, 44.1 kHz) -> expo_bed.wav
import numpy as np, wave, sys
sr=44100; T=60; t=np.arange(sr*T)/sr
chords=[[220,261.63,329.63],[174.61,220,261.63],[261.63,329.63,392],[196,246.94,293.66]]
out=np.zeros_like(t)
for i,c in enumerate(chords*2):
    s,e=i*7.5,i*7.5+9.0
    m=(t>=s)&(t<e); tt=t[m]-s
    env=np.minimum(tt/2.5,1)*np.clip((9.0-tt)/3.0,0,1)
    for f in c:
        for d in (-.4,0,.4):
            out[m]+=np.sin(2*np.pi*(f+d)*tt)*env*.05
        out[m]+=np.sin(2*np.pi*f/2*tt)*env*.04
# soft pulse
beat=(t%1.0); out+=np.sin(2*np.pi*55*t)*np.exp(-beat*5)*.10*np.clip((t-4)/3,0,1)
out*=np.clip(t/2,0,1)*np.clip((T-t)/3,0,1)
out/=np.abs(out).max()*1.15
pcm=(np.stack([out,out*.97],1)*32767).astype('<i2')
w=wave.open(sys.argv[1],'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes()); w.close()
