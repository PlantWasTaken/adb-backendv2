import os
import subprocess
from PIL import Image
import re
import pytesseract
import warnings

class BaseDevice:
    def __init__(self, adb_path=None) -> None:
        self.BASE_RESOLUTION_EMU = [1920,1080] #scale 16:9 aspect ratio
        self.BASE_RESOLUTION_PHN = [2400,1080] #scale, device samsung galaxy s21, 20:9 aspect ratio

        self.BASE_ASPECT_RATIO_EMU = self.BASE_RESOLUTION_EMU[0]/self.BASE_RESOLUTION_EMU[1]
        self.BASE_ASPECT_RATIO_PHN = self.BASE_RESOLUTION_PHN[0]/self.BASE_RESOLUTION_PHN[1]
        self.ORIENTATION = ''

        #for full phone resolution
        self.abs_res_scalar_x = 1 #default 1 
        self.abs_res_scalar_y = 1 #default 1

        #for relative app resolution
        self.rel_res_scalar_x = 1 #default 1 
        self.rel_res_scalar_y = 1 #default 1
        self._currentapp = '' #default ''
        
        current_dir = os.getcwd()
        self.adb = adb_path or self.find_executable('adb.exe', current_dir)
        if not self.adb:
            raise FileNotFoundError("adb.exe not found in the current directory or subdirectories.")
        
        #subprocess.call(['taskkill', '/F', '/IM', 'adb.exe'])
        #server = subprocess.run(f'"{self.adb}" kill-server', shell=True,capture_output=True,text=True)
        server = subprocess.run(f'"{self.adb}" start-server', shell=True,capture_output=True,text=True)
        self.check_connection(server)
        print(server.stderr)

        #subprocess.run(f'"{self.adb}" devices', shell=True)

    def check_connection(self,CompletedProcess):
        if(CompletedProcess.returncode == 0): #good connection
            return True
        else:                                  #bad connection
            raise ConnectionError
        
    def get_info(self, device_identifier) -> None:
        print(f'\nInfo for device: {device_identifier}')
        #subprocess.run(f'"{self.adb}" -s {device_identifier} shell dumpsys battery', shell=True)
        subprocess.run(f'"{self.adb}" -s {device_identifier} shell wm size', check=True, shell=True)
        print(f'App in focus: {self._currentapp}')
        print(f'Orientation: {self.ORIENTATION}')
        print(f'wlan ip: {self.wlan_ip()}')
        #print(f'App in focus res: {self.app_resolution()}')
        #print(f'ABS-Resolution scalar X: {self.abs_res_scalar_x}')
        #print(f'ABS-Resolution scalar Y: {self.abs_res_scalar_y}')
        #print(f'REL-Resolution scalar X: {self.rel_res_scalar_x}')
        #print(f'REL-Resolution scalar Y: {self.rel_res_scalar_y}')
        subprocess.run(f'"{self.adb}" -s {device_identifier} get-serialno', shell=True)

        warnings.warn("DO NOT ATTEMPT TO SCALE ACROSS ASPECT RATIOS")

    def find_executable(self, filename, search_path) -> None:
        """Search for an executable file in the given directory and subdirectories."""
        for root, dirs, files in os.walk(search_path):
            if filename in files:
                return os.path.join(root, filename)
        return None

    def app_resolution(self, device_identifier) -> None: #for tsting
        text = subprocess.run(f'"{self.adb}"  -s {device_identifier} shell dumpsys window | find "app="', shell=True,text=True,capture_output=True)
        words = [i.split() for i in text.stdout.splitlines()]
        current_app_info = words[0]
        current_app_res = [i for i in current_app_info if 'app=' in i]
        app_res = current_app_res[0].replace('app=',"").replace('x', ' ') #first instance
        app_res = app_res.split()
        app_res = [float(i) for i in app_res]
        
        #testing
        #app_res[0] = app_res[0]+80
        return app_res
        #| find "mCurrentConfig"
        #adb shell dumpsys window | find "app="
        #pass

    def screenshot(self, device_identifier) -> Image:
        screenshot_path = os.path.join(os.getcwd(), f'{device_identifier}.png')
        temp_screenshot_path = '/data/local/tmp/image.png'
        
        take_screenshot = subprocess.run(f'"{self.adb}" -s {device_identifier} shell screencap -p {temp_screenshot_path}', shell=True, text=True)
        fetch_screenshot = subprocess.run(f'"{self.adb}" -s {device_identifier} pull {temp_screenshot_path} "{screenshot_path}"', shell=True, text=True)
        
        self.check_connection(take_screenshot)
        self.check_connection(fetch_screenshot)

        return Image.open(screenshot_path)

    def currentfocus(self, device_identifier) -> str:
        _currentfocus = subprocess.run(f'"{self.adb}" -s {device_identifier} shell dumpsys window | find "mCurrentFocus"',shell=True, text=True,capture_output=True)
        self.check_connection(_currentfocus)
        _currentfocus = _currentfocus.stdout.replace("mCurrentFocus=","")

        return _currentfocus.strip()

    def text_input(self, device_identifier, text) -> None:
        text = text.replace(" ", "%s")
        subprocess.run(f'"{self.adb}" -s {device_identifier} shell input text {text}',shell=True, text=True,capture_output=True)

    def keyevent_input(self, device_identifier, code) -> None:
        try:
            code = int(code)
        except:
            print(f'Code not {int}')
            return None
        r = subprocess.run(f'"{self.adb}" -s {device_identifier} shell input keyevent {code}',shell=True, text=True,capture_output=True)
        self.check_connection(r)

    def orientation(self, device_identifier) -> str:
        orientation = subprocess.run(f'"{self.adb}" -s {device_identifier} shell dumpsys window | find "mCurrentRotation"',shell=True, text=True,capture_output=True)
        self.check_connection(orientation)

        _orientation = orientation.stdout.replace("mCurrentRotation=", "")
        #ROTATION_0 AND ROTATION_360 ARE THE SAME, PORTRAIT
        #ROTATION_90 AND ROTATION_270 ARE THE SAME, LANDSCAPE

        return _orientation.strip()

    def resolution(self, device_identifier) -> list:
        res = subprocess.run(f'"{self.adb}" -s {device_identifier} shell wm size', shell=True, text=True, capture_output=True)
        self.check_connection(res) 
        #self.check_connection(orientation) #uncomment

        res = res.stdout.split()[-1] #formattex in mxn, type=str
        res_list = res.replace('x', ' ').split()
        res_list_int = list(map(int, res_list))
        res_list_int.sort(reverse=True) #sort x,y

        return res_list_int #in the format, x is biggest, y smallest

    def wlan_ip(self, device_identifier) -> str:
        wlan_ip = subprocess.run(f'"{self.adb}" -s {device_identifier} shell ip addr show wlan0', shell=True, text=True, capture_output=True)
        self.check_connection(wlan_ip)

        wlan_ip = wlan_ip.stdout.splitlines()
        wlan_ip = [i for i in wlan_ip if 'inet' in i]
        wlan_ip = [i.split() for i in wlan_ip]
        wlan_ip = [i[1] for i in wlan_ip]

        return wlan_ip[0]

    def screenInput(self, device_identifier, x, y) -> None: #dont print out
        #print(f'Input {device_identifier} at: {x}, {y}')
        subprocess.Popen(f'"{self.adb}" -s {device_identifier} shell input tap {x} {y}', shell=True, text=True)

    def screenSwipe(self, device_identifier, x1, y1, x2, y2) -> None: #dont print out
        #print(f'Swiping from: {x1}, {y1} -> {x2}, {y2}')
        subprocess.Popen(f'"{self.adb}" -s {device_identifier} shell input touchscreen swipe {x1} {y1} {x2} {y2}', shell=True)

    def kill_connection(self, device_identifier) -> None:
        #print(f'Killing connection to {device_identifier}')
        subprocess.Popen(f'"{self.adb}" -s {device_identifier} kill-server', shell=True)


class Phone(BaseDevice):
    def __init__(self, name, vertical=True,adb_path=None) -> None:
        super().__init__(adb_path)
        self.name = name #device name
        
        subprocess.run(f'"{self.adb}" devices', shell=True)
        if(self.name == None): #unknown device name
            self.name = self.find_device()

            for i in self.name: #if multiple devices
                print(f'Found device with name: {i}')
            
            self.name = self.name[0] #unit 0, is the default unit
            print(f'Connecting to default unit: {self.name}')
            print(f'Recomended to change device name to: {self.name}\nTo avoid errors.')

        phone_resolution = self.resolution() #[x,y]
        current_focus_app_resolution = self.app_resolution() #[x,y]

        self.ORIENTATION = self.orientation() #str
        self._currentapp = self.currentfocus() #str

        if(self.ORIENTATION == 'ROTATION_90' or self.ORIENTATION == 'ROTATION_270'):
            self.abs_res_scalar_x = phone_resolution[0]/self.BASE_RESOLUTION_EMU[0] #eg 2400/1920
            self.abs_res_scalar_y = phone_resolution[1]/self.BASE_RESOLUTION_EMU[1]
        else:
            self.abs_res_scalar_x = phone_resolution[1]/self.BASE_RESOLUTION_EMU[0]
            self.abs_res_scalar_y = phone_resolution[0]/self.BASE_RESOLUTION_EMU[1]

        self.rel_res_scalar_x = current_focus_app_resolution[0]/self.BASE_RESOLUTION_EMU[0]
        self.rel_res_scalar_y = current_focus_app_resolution[1]/self.BASE_RESOLUTION_EMU[1]

        print(current_focus_app_resolution[0],self.BASE_RESOLUTION_EMU[0],current_focus_app_resolution[0]/self.BASE_RESOLUTION_EMU[0])
        print(current_focus_app_resolution[1],self.BASE_RESOLUTION_EMU[1],current_focus_app_resolution[1]/self.BASE_RESOLUTION_EMU[1])
        self.get_info() #post info about system
        #subprocess.run(f'"{self.adb}" -s {self.name} shell wm size', check=True)

    def find_device(self) -> str: 
        print(f'Finding device..')
        devices_output = subprocess.run(f'"{self.adb}" devices', shell=True, capture_output=True, text=True)
        super().check_connection(devices_output)

        phones = devices_output.stdout.split() #list
        phones = phones[4:] #formatting
        device_name = [i for i in phones if i != 'device']
        phone_name = [name for name in device_name if 'emulator' not in name]

        if(phone_name == []): #no phone
            raise ConnectionError
        
        return phone_name

    def get_info(self) -> None:
        super().get_info(self.name)
    
    def screenshot(self) -> Image:
        return super().screenshot(self.name)

    def screenInput(self, x, y) -> None: #scaled
        x_scaled = x*self.abs_res_scalar_x #scaling values for normalization
        y_scaled = y*self.abs_res_scalar_y

        super().screenInput(self.name, x_scaled, y_scaled)

    def screenSwipe(self, x1, y1, x2, y2) -> None:
        x1_scaled = x1*self.abs_res_scalar_x #scaling values for normalization
        y1_scaled = y1*self.abs_res_scalar_y
        x2_scaled = x2*self.abs_res_scalar_x 
        y2_scaled = y2*self.abs_res_scalar_y

        super().screenSwipe(self.name, x1_scaled, y1_scaled, x2_scaled, y2_scaled)

    def text_input(self, text) -> None:
        super().text_input(self.name, text)

    def keyevent_input(self, code) -> None:
        super().keyevent_input(self.name, code)
        
    def resolution(self) -> list:
        res = super().resolution(self.name)
        return res

    def orientation(self) -> str:
        ori = super().orientation(self.name)
        return ori

    def currentfocus(self) -> str:
        focus = super().currentfocus(self.name)
        return focus

    def app_resolution(self) -> None:
        res = super().app_resolution(self.name)
        return res

class Emulator(BaseDevice):
    def __init__(self, port, devices, emulator=True,name=None, adb_path=None) -> None:
        super().__init__(adb_path)
        self.port = port
        self.devices = devices
        self.emulator = emulator
        self.name = name

        if self.emulator:
            self.connect_emulators()
        else:
            raise SystemError

        self.identifier = f"emulator-{self.port}" if self.emulator else self.name #may cause issues

        self.ORIENTATION = self.orientation() #str
        self._currentapp = self.currentfocus() #str

        emulator_resolution = self.resolution() #[x,y]
        current_focus_app_resolution = self.app_resolution() #[x,y]
 
        self.abs_res_scalar_x = emulator_resolution[0]/self.BASE_RESOLUTION_EMU[0] #phone -> emulator abs resolution
        self.abs_res_scalar_y = emulator_resolution[1]/self.BASE_RESOLUTION_EMU[1]

        self.rel_res_scalar_x = current_focus_app_resolution[0]/self.BASE_RESOLUTION_EMU[0] #phone -> amulator app resolution
        self.rel_res_scalar_y = current_focus_app_resolution[1]/self.BASE_RESOLUTION_EMU[1]

        self.get_info() #post info about system

    def generate_ports(self) -> list:
        if self.devices == 0:
            print(f'Finding devices..')

            #kill_server = subprocess.run(f'"{self.adb}" kill-server', shell=True, capture_output=True, text=True)
            start_server = subprocess.run(f'"{self.adb}" start-server', shell=True, capture_output=True, text=True)
            devices_output = subprocess.run(f'"{self.adb}" devices', shell=True, capture_output=True, text=True)
            super().check_connection(devices_output)

            emulator_ports = re.findall(r'emulator-(\d+)', devices_output.stdout)
            ports = [int(port) for port in emulator_ports]

            if not ports:
                print(f'No adb device detected')
                #raise SystemError
            else:
                self.devices = len(ports)
                print(f'Found {len(ports)} devices')
                print(f'Ports: {ports}')

        if self.devices == -1: #manual port
            return [self.port]

        if self.devices == 1: #default port
            return [5554]
        
        if self.devices == 2:
            return[5554,5558]
        
        if self.devices > 2:
            return [(5554 + 2 * i) for i in range(self.devices)]

    def connect_emulators(self) -> None:
        ports = self.generate_ports()
        print(f'Ports: {ports}')

        if(self.port not in ports):
            print(f'Port: {self.port} not found')
            print(f'Defaulting to: {5554}')
            self.port = 5554
        
        for port in ports:
            print(f'Connecting to port: {port}')
            try:
                #kill_server = subprocess.run(f'"{self.adb}" -s emulator-{port} kill-server', shell=True, capture_output=True, text=True)
                start_server = subprocess.run(f'"{self.adb}" -s emulator-{port} start-server', shell=True, capture_output=True, text=True)
                subprocess.run(f'"{self.adb}" -s emulator-{port} shell wm size', check=True)

            except subprocess.CalledProcessError:
                print(f'Failed to connect to port: {port}')
                continue

    def get_info(self):
        return super().get_info(self.identifier)
    
    def screenshot(self) -> Image:
        return super().screenshot(self.identifier)

    def screenInput(self, x, y) -> None: 
        x_scaled = x*self.abs_res_scalar_x #scaling values for normalization
        y_scaled = y*self.abs_res_scalar_y

        super().screenInput(self.identifier, x_scaled, y_scaled)

    def screenSwipe(self, x1, y1, x2, y2) -> None:
        x1_scaled = x1*self.abs_res_scalar_x #scaling values for normalization
        y1_scaled = y1*self.abs_res_scalar_y
        x2_scaled = x2*self.abs_res_scalar_x 
        y2_scaled = y2*self.abs_res_scalar_y

        super().screenSwipe(self.identifier, x1_scaled, y1_scaled, x2_scaled, y2_scaled)

    def text_input(self, text) -> None:
        super().text_input(self.identifier, text)

    def keyevent_input(self, code) -> None:
        super().keyevent_input(self.identifier, code)

    def resolution(self):
        return super().resolution(self.identifier)

    def currentfocus(self) -> str:
        focus = super().currentfocus(self.identifier)
        return focus

    def orientation(self) -> str:
        ori = super().orientation(self.identifier)
        return ori

    def app_resolution(self) -> None:
        res = super().app_resolution(self.identifier)
        return res
    
    def wlan_ip(self) -> str:
        wlan_ip = super().wlan_ip(self.identifier)
        return wlan_ip
    
    def kill_connection(self) -> None:
        super().kill_connection(self.identifier)

class ImageOcr:
    def __init__(self,im) -> None:
        # Search for tesseract.exe in the current directory or subdirectories
        current_dir = os.getcwd()
        tesseract_path = self.find_executable('tesseract.exe', current_dir)
        if not tesseract_path:
            raise FileNotFoundError("tesseract.exe not found in the current directory or subdirectories.")
        
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

        self.im = im 
        self.BASE_RESOLUTION_EMU = [1920,1080] #scale 16:9 aspect ratio
        self.BASE_RESOLUTION_PHN = [2400,1080] #scale, device samsung galaxy s21, 9:20 aspect ratio

    def find_executable(self, filename, search_path) -> None:
        for root, dirs, files in os.walk(search_path):
            if filename in files:
                return os.path.join(root, filename)
        return None

    def crop_image(self,x1,y1,x2,y2,res_scalar_x,res_scalar_y) -> Image:
        x1_scaled = x1*res_scalar_x #scaling values for normalization
        y1_scaled = y1*res_scalar_y
        x2_scaled = x2*res_scalar_x 
        y2_scaled = y2*res_scalar_y

        _im = self.im.crop((x1_scaled, y1_scaled, x2_scaled, y2_scaled))
        return _im
    
    def get_text(self) -> str:
        # Extracting text from the image using pytesseract
        text = pytesseract.image_to_string(self.im).split()
        return text