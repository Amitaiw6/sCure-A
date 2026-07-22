import { writeFileSync } from 'fs'

// Cure-process actuator/setpoint timing diagram (inline SVG for the SRS §7.7).
// Phase sequence: Drying -> Heating -> Cure -> Cooling -> N2 (N2 fill is the final state).
// Regenerate:  node tools/gen-timing.mjs docs/screenshots/timing.svg

// ---- timeline (x) ----
const X={ start:210, dStart:310, dEnd:470, hEnd:620, cEnd:850, coolEnd:1050, nEnd:1230, tail:1300 }
const rampS=500, ledOn=X.hEnd            // LED start window: on ramp start (rampS) .. at target / cure start (ledOn)
const regionsX=[['lead',X.start,X.dStart],['dry',X.dStart,X.dEnd],['heat',X.dEnd,X.hEnd],['cure',X.hEnd,X.cEnd],['cool',X.cEnd,X.coolEnd],['n2',X.coolEnd,X.nEnd],['tail',X.nEnd,X.tail]]

// ---- colors ----
const MAG='#e24bad', BLUE='#4a90d9', GREEN='#2e9e5b', RED='#e53935', OLIVE='#9a9a17',
      BLACK='#111', GOLD='#f2b705', GOLDD='#b58704', VIOLET='#8a5cf5', TEAL='#17a2b8'

// ---- row y-levels ----
const R={
  damperHi:95, damperLo:145,
  fanHi:195,   fanLo:245,
  nvHi:295,    nvLo:345,
  ncHi:395,    ncLo:445,
  tcHi:495,    tcLo:545,
  heater:595,
  tUV:645, tDry:705, tCool:765,
  u4Hi:835, u4Lo:885,
  u5Hi:935, u5Lo:985,
  lcHi:1035, lcLo:1085,
}
const W=1360, H=1170

function digital(vals, yHi, yLo){
  const pts=[]
  for(const [name,xa,xb] of regionsX){ const y=vals[name]==='hi'?yHi:yLo; pts.push([xa,y],[xb,y]) }
  return pts
}
const poly=(pts,color,w=3,dash='')=>`<polyline fill="none" stroke="${color}" stroke-width="${w}"${dash?` stroke-dasharray="${dash}"`:''} points="${pts.map(p=>p.join(',')).join(' ')}"/>`
const rect=(x,y,w,h,fill,op)=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" opacity="${op}"/>`
const txt=(x,y,s,color='#111',anchor='end',size=14,weight='normal')=>`<text x="${x}" y="${y}" fill="${color}" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" dominant-baseline="middle">${s}</text>`

const p=[]
// axes
p.push(`<line x1="${X.start}" y1="30" x2="${X.start}" y2="1115" stroke="#2b4a6b" stroke-width="3"/>`)
p.push(`<line x1="${X.start}" y1="1115" x2="${X.tail}" y2="1115" stroke="#2b4a6b" stroke-width="3"/>`)
// phase dividers + labels
for(const [x,c] of [[X.dStart,'#5a9e3a'],[X.dEnd,'#5a9e3a'],[X.hEnd,BLUE],[X.cEnd,RED],[X.coolEnd,TEAL],[X.nEnd,GREEN]])
  p.push(`<line x1="${x}" y1="40" x2="${x}" y2="1132" stroke="${c}" stroke-width="1.5" stroke-dasharray="5 5" opacity="0.75"/>`)
for(const [s,c,x] of [['Drying','#5a9e3a',(X.dStart+X.dEnd)/2],['Heating',RED,(X.dEnd+X.hEnd)/2],['Cure','#e07b1a',(X.hEnd+X.cEnd)/2],['cooling',TEAL,(X.cEnd+X.coolEnd)/2],['N2',GREEN,(X.coolEnd+X.nEnd)/2]]){
  p.push(`<rect x="${x-48}" y="1132" width="96" height="26" rx="6" fill="#fff" stroke="#d7dde3"/>`)
  p.push(txt(x,1145,s,c,'middle',15,'bold'))
}

// 1 Damper (open in dry & cool)
p.push(poly(digital({lead:'lo',dry:'hi',heat:'lo',cure:'lo',cool:'hi',n2:'lo',tail:'lo'},R.damperHi,R.damperLo),MAG))
p.push(txt(X.start-14,R.damperHi,'Damper (open)',MAG)); p.push(txt(X.start-14,R.damperLo,'Damper (close)',MAG))
// 2 Air-in fan (raised in dry & cool)
p.push(poly(digital({lead:'lo',dry:'hi',heat:'lo',cure:'lo',cool:'hi',n2:'lo',tail:'lo'},R.fanHi,R.fanLo),BLUE))
p.push(txt(X.start-14,(R.fanHi+R.fanLo)/2,'Air in Fan (PWM)',BLUE))
// 3 N2 valve — open for the whole (final) N2 phase (fill)
p.push(poly(digital({lead:'lo',dry:'lo',heat:'lo',cure:'lo',cool:'lo',n2:'hi',tail:'lo'},R.nvHi,R.nvLo),GREEN))
p.push(txt(X.start-14,R.nvHi,'N2 valve (open)',GREEN)); p.push(txt(X.start-14,R.nvLo,'N2 valve (close)',GREEN))
p.push(txt((X.coolEnd+X.nEnd)/2,R.nvHi-13,'fill (preset duration)',GREEN,'middle',11,'bold'))
// 4 N2 in chamber — present from the final N2 fill onward
p.push(poly(digital({lead:'lo',dry:'lo',heat:'lo',cure:'lo',cool:'lo',n2:'hi',tail:'hi'},R.ncHi,R.ncLo),GREEN))
p.push(txt(X.start-14,R.ncHi,'N2 in chamber (present)',GREEN)); p.push(txt(X.start-14,R.ncLo,'N2 in chamber (vented)',GREEN))
// 5 Temperature control (on until cooling)
p.push(poly(digital({lead:'hi',dry:'hi',heat:'hi',cure:'hi',cool:'lo',n2:'lo',tail:'lo'},R.tcHi,R.tcLo),RED))
p.push(txt(X.start-14,R.tcHi,'Temperature Control (on)',RED)); p.push(txt(X.start-14,R.tcLo,'Temperature Control (off)',RED))
// 6 Fan heater (flat)
p.push(poly([[X.start,R.heater],[X.tail,R.heater]],OLIVE))
p.push(txt(X.start-14,R.heater,'Fan heater (PWM)',OLIVE))
// 7 Temp setpoint (analog)
for(const y of [R.tUV,R.tDry,R.tCool]) p.push(`<line x1="${X.start}" y1="${y}" x2="${X.tail}" y2="${y}" stroke="#000" stroke-width="0.5" stroke-dasharray="2 6" opacity="0.15"/>`)
p.push(poly([[X.start,R.tCool],[X.dStart,R.tCool],[X.dEnd,R.tDry],[X.dEnd+30,R.tDry],[X.hEnd,R.tUV],[X.cEnd,R.tUV],[X.coolEnd,R.tCool+5],[X.tail,R.tCool+5]],BLACK,3.5))
p.push(txt(X.start-14,R.tUV,'UV temp setpoint',BLACK)); p.push(txt(X.start-14,R.tDry,'Drying temp setpoint',BLACK)); p.push(txt(X.start-14,R.tCool,'Cooling temp setpoint',BLACK))
// 8 UV LED 405 nm (Cure)
p.push(rect(rampS,R.u4Hi,ledOn-rampS,R.u4Lo-R.u4Hi,GOLD,0.14))
p.push(poly([[X.start,R.u4Lo],[ledOn,R.u4Lo],[ledOn,R.u4Hi],[X.cEnd,R.u4Hi],[X.cEnd,R.u4Lo],[X.tail,R.u4Lo]],GOLD))
p.push(poly([[rampS,R.u4Lo],[rampS,R.u4Hi],[ledOn,R.u4Hi]],GOLD,2.5,'7 5'))
p.push(txt(X.start-14,R.u4Hi,'UV LED 405 nm (on)',GOLD)); p.push(txt(X.start-14,R.u4Lo,'off',GOLD))
p.push(txt((rampS+ledOn)/2,R.u4Hi-13,'LED start: on ramp start (dashed)  ↔  at target (solid)',GOLDD,'middle',12,'bold'))
// 9 UV LED 450 nm (Bleaching) — dashed alternative during Cure
p.push(poly([[X.start,R.u5Lo],[X.tail,R.u5Lo]],VIOLET,2))
p.push(poly([[ledOn,R.u5Lo],[ledOn,R.u5Hi],[X.cEnd,R.u5Hi],[X.cEnd,R.u5Lo]],VIOLET,2.5,'7 5'))
p.push(txt(X.start-14,R.u5Hi,'UV LED 450 nm (on)',VIOLET)); p.push(txt(X.start-14,R.u5Lo,'off',VIOLET))
p.push(txt((X.hEnd+X.cEnd)/2,R.u5Hi-13,'alternative — 450 nm for a Bleaching step (one wavelength per step)',VIOLET,'middle',11,'bold'))
// 10 LED cooling — follows the active LED (same choice window)
p.push(rect(rampS,R.lcHi,ledOn-rampS,R.lcLo-R.lcHi,TEAL,0.12))
p.push(poly([[X.start,R.lcLo],[ledOn,R.lcLo],[ledOn,R.lcHi],[X.cEnd,R.lcHi],[X.cEnd,R.lcLo],[X.tail,R.lcLo]],TEAL))
p.push(poly([[rampS,R.lcLo],[rampS,R.lcHi],[ledOn,R.lcHi]],TEAL,2.5,'7 5'))
p.push(txt(X.start-14,(R.lcHi+R.lcLo)/2,'LED cooling system (PWM)',TEAL))

const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;min-width:1040px;display:block" font-family="Segoe UI, Arial, sans-serif">
<rect width="${W}" height="${H}" fill="#fff"/>
${p.join('\n')}
</svg>`
writeFileSync(process.argv[2], svg)
console.log('wrote', process.argv[2], svg.length,'bytes')