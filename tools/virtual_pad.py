import sys; 

sys.path.insert(0, 'tests/behavioral')

from harness.virtual_pad import VirtualPad

p = VirtualPad()
print('pad:', p.device_path)
input('Enter = disconnect\n')
p.close()
