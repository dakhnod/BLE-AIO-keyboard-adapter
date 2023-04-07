import bleak
import yaml
import argparse
import asyncio
import pynput
import dataclasses

class AIOKeyboardAdapter:
    @dataclasses.dataclass
    class Binding():
        key: int|str
        auto_release: bool


    def __init__(self, config) -> None:
        self.config = config
        self.keyboard = pynput.keyboard.Controller()
    
    def get_binding_by_sensor_index(self, index) -> Binding:
        bindings = self.config.get('bindings', [])

        def find_by_index():
            for binding in bindings:
                if isinstance(binding, dict) and binding.get('sensor', -1) == index:
                    return binding

            return bindings[index]

        result = find_by_index()
        if result is None:
            return None

        auto_release_default = self.config.get('auto_release', True)

        if isinstance(result, int):
            return self.Binding(pynput.keyboard.KeyCode(result), auto_release_default)
        if isinstance(result, str):
            return self.Binding(result, auto_release_default)

        return self.Binding(result['key'], result.get('auto_release', auto_release_default))

    async def connect(self):
        scanner = bleak.BleakScanner()
        device = await scanner.find_device_by_name(self.config['name'], 60)

        self.client = bleak.BleakClient(device)
        await self.client.connect()

        io_service = self.client.services['00001815-0000-1000-8000-00805f9b34fb']
        for characteristic in io_service.characteristics:
            if characteristic.uuid == '00002a56-0000-1000-8000-00805f9b34fb' and 'notify' in characteristic.properties:
                input_characteristic = characteristic
                break
        else:
            raise RuntimeError('Input IO characteristic not found')
        def handle_input(characteristic, data):
            print(characteristic, data)
            for byte_index in range(len(data)):
                for bit_index in range(0, 8, 2):
                    bits = (data[byte_index] >> bit_index) & 0b11
                    if bits == 0b11:
                        continue
                    is_pressed = bits == 0b01
                    pin_index = byte_index * 4 + int(bit_index / 2)
                    print(f'Pin {pin_index} is pressed: {is_pressed}')
                    binding = self.get_binding_by_sensor_index(pin_index)
                    if binding is None:
                        print('no binding specified for pin')
                        return
                    if is_pressed:
                        self.keyboard.press(binding.key)
                        if binding.auto_release:
                            self.keyboard.release(binding.key)
                    elif not binding.auto_release:
                        self.keyboard.release(binding.key)
        await self.client.start_notify(input_characteristic, handle_input)
        print('waiting for notifications')
        await asyncio.Future()
        pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', '-c', required=True)
    args = parser.parse_args()

    with open(args.config, 'r') as file:
        config = yaml.load(file, yaml.Loader)

    adapter = AIOKeyboardAdapter(config)
    asyncio.run(adapter.connect())