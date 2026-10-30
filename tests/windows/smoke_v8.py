import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from types import SimpleNamespace as NS
from atomman_lhm_direct import DirectCpuReader
from atomman_touch_volume import EventDecoder, self_test

class HW:
    HardwareType = 'Cpu'
    def __init__(self):
        self.Sensors = [
            NS(Name='CPU Package', SensorType='Power', Value=22.3, Identifier='/intelcpu/0/power/0'),
            NS(Name='Core Max', SensorType='Temperature', Value=64, Identifier='/intelcpu/0/temperature/0'),
            NS(Name='CPU Package', SensorType='Temperature', Value=55, Identifier='/intelcpu/0/temperature/18'),
            NS(Name='CPU Package Distance to TjMax', SensorType='Temperature', Value=57, Identifier='/intelcpu/0/temperature/19')]
    def Update(self):
        pass
fake = NS(Hardware=[HW(), NS(HardwareType='GpuNvidia', Sensors=[NS(Name='GPU Core', SensorType='Temperature', Value=70, Identifier='/gpu-nvidia/0/temperature/0')])])
temp, source = DirectCpuReader._find_cpu_sensor(fake)
assert (temp, source) == (55, '/intelcpu/0/temperature/18'),(temp,source)
fake.Hardware[0].Sensors = fake.Hardware[0].Sensors[:1]
assert DirectCpuReader._find_cpu_sensor(fake) == (0,None)

self_test()
print('[v8] CPU sensor type and preference tests passed')

import sys
sys.argv = ['screen_windows.py','--touch-self-test']
import screen_windows
screen_windows.main()
print('[v8] adapter CLI smoke test passed')
