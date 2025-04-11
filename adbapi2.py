import os
import re
import time
import logging
import subprocess
from typing import Optional, List, Tuple, Union
from PIL import Image, ImageDraw, ImageFilter
import pytesseract
import cv2
import numpy as np
from io import BytesIO

os.environ['OMP_THREAD_LIMIT'] = '8'
os.environ['TESSDATA_PREFIX'] = os.path.join(os.getcwd(), 'tessdata')
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ADBAPI')

class BaseDevice:
    def __init__(self, adb_path: Optional[str] = None) -> None:
        # Original resolution constants
        self.BASE_RESOLUTION_EMU = [1920, 1080]  # 16:9 aspect ratio
        self.BASE_RESOLUTION_PHN = [2400, 1080]  # 20:9 aspect ratio (Samsung Galaxy S21)
        
        # Original scaling factors
        self.abs_res_scalar_x = 1.0
        self.abs_res_scalar_y = 1.0
        self.rel_res_scalar_x = 1.0
        self.rel_res_scalar_y = 1.0
        self.ORIENTATION = ''
        self._currentapp = ''
        
        # Find ADB executable (original logic with improved validation)
        current_dir = os.getcwd()
        self.adb = adb_path or self.find_executable('adb.exe' if os.name == 'nt' else 'adb', current_dir)
        if not self.adb:
            raise FileNotFoundError("adb executable not found in the current directory or subdirectories.")
        
        # Establish connection (improved version)
        self._establish_secure_connection()

    def find_executable(self, filename: str, search_path: str) -> Optional[str]:
        for root, dirs, files in os.walk(search_path):
            if filename in files:
                return os.path.join(root, filename)
        return None

    def check_connection(self, completed_process: subprocess.CompletedProcess) -> bool:
        if completed_process.returncode != 0:
            raise ConnectionError(completed_process.stderr)
        else: return True

    def _establish_secure_connection(self, max_retries: int = 3) -> None:
        for attempt in range(max_retries):
            try:
                # Verify server is responsive
                result = subprocess.run(
                    [self.adb, 'devices'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    logger.debug("ADB server is responsive")
                    return
                
                # Start server if needed
                start_result = subprocess.run(
                    [self.adb, 'start-server'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if start_result.returncode != 0:
                    raise ConnectionError(f"Failed to start ADB server: {start_result.stderr}")
                
                logger.info("ADB server started successfully")
                return
                
            except subprocess.TimeoutExpired:
                logger.warning(f"Connection attempt {attempt + 1} timed out")
                if attempt == max_retries - 1:
                    raise ConnectionError("ADB server not responding after multiple attempts")
                time.sleep(1)

    def get_info(self, device_identifier: str) -> None:
        logger.info(f"\nInfo for device: {device_identifier}")
        logger.info(f"Resolution: {self.resolution()}")
        logger.info(f"App in focus: {self._currentapp}")
        logger.info(f"Orientation: {self.ORIENTATION}")
        logger.info(f"wlan ip: {self.wlan_ip(device_identifier)}")
        subprocess.run(f'"{self.adb}" -s {device_identifier} get-serialno', shell=True)

    def app_resolution(self, device_identifier: str) -> List[float]:
        text = subprocess.run(
            f'"{self.adb}" -s {device_identifier} shell dumpsys window | find "app="',
            shell=True, text=True, capture_output=True
        )
        words = [i.split() for i in text.stdout.splitlines()]
        current_app_info = words[0]
        current_app_res = [i for i in current_app_info if 'app=' in i]
        app_res = current_app_res[0].replace('app=', "").replace('x', ' ')
        return [float(i) for i in app_res.split()]

    def screenshot(self, device_identifier: str) -> Image.Image:
        timestamp = time.time()

        # Run the screencap command to capture the screenshot directly to stdout
        result = subprocess.run(
            f'"{self.adb}" -s {device_identifier} exec-out screencap -p',
            shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # Check for errors in stderr
        if result.stderr:
            print(f"Error in capturing screenshot: {result.stderr.decode()}")
            return None

        # The screenshot image is now in stdout, which we can read directly into a PIL Image
        screenshot_data = result.stdout

        # Create a BytesIO object from the screenshot data
        image = Image.open(BytesIO(screenshot_data))

        print(f'Screenshot time: {time.time() - timestamp}')
        return image


    def currentfocus(self, device_identifier: str) -> str:
        _currentfocus = subprocess.run(
            f'"{self.adb}" -s {device_identifier} shell dumpsys window | find "mCurrentFocus"',
            shell=True, text=True, capture_output=True
        )
        self.check_connection(_currentfocus)
        return _currentfocus.stdout.replace("mCurrentFocus=", "").strip()

    def text_input(self, device_identifier: str, text: str) -> None:
        text = text.replace(" ", "%s")
        subprocess.run(
            f'"{self.adb}" -s {device_identifier} shell input text {text}',
            shell=True, text=True, capture_output=True
        )

    def keyevent_input(self, device_identifier: str, code: Union[int, str]) -> None:
        try:
            code = int(code)
            subprocess.run(
                f'"{self.adb}" -s {device_identifier} shell input keyevent {code}',
                shell=True, text=True, capture_output=True
            )
        except ValueError:
            logger.error(f"Invalid keyevent code: {code}")

    def orientation(self, device_identifier: str) -> str:
        orientation = subprocess.run(
            f'"{self.adb}" -s {device_identifier} shell dumpsys window | find "mCurrentRotation"',
            shell=True, text=True, capture_output=True
        )
        self.check_connection(orientation)
        return orientation.stdout.replace("mCurrentRotation=", "").strip()

    def resolution(self, device_identifier: str) -> List[int]:
        orientation = self.orientation()

        res = subprocess.run(
            f'"{self.adb}" -s {device_identifier} shell wm size',
            shell=True, text=True, capture_output=True
        )
        self.check_connection(res)
        res = res.stdout.split()[-1]

        if orientation == 'ROTATION_90' or orientation == 'ROTATION_270': #roation logic
            res = res.replace('x', ' ').split()[1] + 'x' + res.replace('x', ' ').split()[0]
        return list(map(int, res.replace('x', ' ').split()))

    def wlan_ip(self, device_identifier: str) -> str:
        try:
            result = subprocess.run(
                f'"{self.adb}" -s {device_identifier} shell ip addr show wlan0',
                shell=True, 
                text=True, 
                capture_output=True
            )
            if result.returncode != 0:
                return "N/A"
                
            lines = [line.split() for line in result.stdout.splitlines() if 'inet' in line]
            return lines[0][1].split('/')[0] if lines else "N/A"
        except Exception:
            return "N/A"

    def screenInput(self, device_identifier: str, x: int, y: int) -> None:
        subprocess.Popen(
            f'"{self.adb}" -s {device_identifier} shell input tap {x} {y}',
            shell=True, text=True
        )

    def screenSwipe(self, device_identifier: str, x1: int, y1: int, x2: int, y2: int) -> None:
        print('swipe')
        subprocess.Popen(
            f'"{self.adb}" -s {device_identifier} shell input touchscreen swipe {x1} {y1} {x2} {y2}',
            shell=True
        )

    def kill_connection(self, device_identifier: str) -> None:
        subprocess.Popen(f'"{self.adb}" -s {device_identifier} kill-server',shell=True)

class Phone(BaseDevice):
    def __init__(self, name: str, vertical: bool = True, adb_path: Optional[str] = None) -> None:
        super().__init__(adb_path)
        self.name = name
        self.identifier = self.name
        
        if not name:
            found = self.find_device()
            if not found:
                raise ConnectionError("No phone devices found")
            self.name = found[0]

            logger.info(f"Auto-selected device: {self.name}")

        # Original resolution scaling logic
        phone_res = self.resolution()
        app_res = self.app_resolution()
        self.ORIENTATION = self.orientation()
        self._currentapp = self.currentfocus()

        if self.ORIENTATION in ('ROTATION_90', 'ROTATION_270'):
            self.abs_res_scalar_x = phone_res[0] / self.BASE_RESOLUTION_EMU[0]
            self.abs_res_scalar_y = phone_res[1] / self.BASE_RESOLUTION_EMU[1]
        else:
            self.abs_res_scalar_x = phone_res[1] / self.BASE_RESOLUTION_EMU[0]
            self.abs_res_scalar_y = phone_res[0] / self.BASE_RESOLUTION_EMU[1]

        self.rel_res_scalar_x = app_res[0] / self.BASE_RESOLUTION_EMU[0]
        self.rel_res_scalar_y = app_res[1] / self.BASE_RESOLUTION_EMU[1]
        
        self.get_info()

    def find_device(self) -> List[str]:
        devices_output = subprocess.run(
            f'"{self.adb}" devices',
            shell=True, capture_output=True, text=True
        )
        
        phones = devices_output.stdout.split()
        phones = phones[4:]
        return [i for i in phones if i != 'device' and 'emulator' not in i]

    def get_battery_info(self) -> dict:
        result = subprocess.run(
            f'"{self.adb}" -s {self.name} shell dumpsys battery',
            shell=True, text=True, capture_output=True
        )
        info = {}
        for line in result.stdout.splitlines():
            if ':' in line:
                key, value = line.strip().split(':', 1)
                info[key.strip()] = value.strip()
        return info

    def get_android_version(self) -> str:
        result = subprocess.run(
            f'"{self.adb}" -s {self.name} shell getprop ro.build.version.release',
            shell=True, text=True, capture_output=True
        )
        return result.stdout.strip()

    def get_sdk_version(self) -> str:
        result = subprocess.run(
            f'"{self.adb}" -s {self.name} shell getprop ro.build.version.sdk',
            shell=True, text=True, capture_output=True
        )
        return result.stdout.strip()

    def get_device_model(self) -> str:
        result = subprocess.run(
            f'"{self.adb}" -s {self.name} shell getprop ro.product.model',
            shell=True, text=True, capture_output=True
        )
        return result.stdout.strip()

    def get_manufacturer(self) -> str:
        result = subprocess.run(
            f'"{self.adb}" -s {self.name} shell getprop ro.product.manufacturer',
            shell=True, text=True, capture_output=True
        )
        return result.stdout.strip()

    def get_total_storage(self) -> str:
        result = subprocess.run(
            f'"{self.adb}" -s {self.name} shell df /data',
            shell=True, text=True, capture_output=True
        )
        lines = result.stdout.splitlines()
        if len(lines) >= 2:
            return lines[1].split()[1]  # 2nd line, 2nd column typically = total space
        return "Unknown"
    
    def get_current_wifi_info(self) -> dict:
        output = subprocess.check_output(["adb", "shell", "dumpsys", "wifi"], text=True)

        def search(pattern):
            match = re.search(pattern, output)
            return match.group(1).strip() if match else None

        info = {
            "SSID": search(r'SSID: "(.+?)"'),
            "BSSID": search(r'BSSID: ([0-9a-fA-F:]+)'),
            "Signal Strength (RSSI)": search(r'rssi: (-\d+)'),
            "Link Speed": search(r'linkSpeed: (\d+ \w+)'),
            "Frequency": search(r'frequency: (\d+)'),
            "Supplicant State": search(r'Supplicant state: (\w+)'),
            "Network ID": search(r'networkId: (\d+)'),
            "Hidden SSID": search(r'hiddenSSID: (\w+)'),
            "IP Assignment": search(r'ipAssignment: (\w+)'),
            "Proxy Settings": search(r'proxySettings: (\w+)'),
            "Metered": search(r'meteredHint: (\w+)'),
            "Wi-Fi Standard": search(r'Standard: ([^\n]+)'),
            "Tx Bitrate": search(r'txBitrate: (\d+)'),
            "Rx Bitrate": search(r'rxBitrate: (\d+)'),
            "Channel Width": search(r'Channel Width: ([^\n]+)'),
            "Roaming": search(r'roaming: (\w+)'),
            "Score": search(r'score: (\d+)'),
        }

        return info

    def get_current_wifi_info(self):
        result = subprocess.run(
            f'"{self.adb}" -s {self.name} shell dumpsys wifi',
            shell=True, text=True, capture_output=True
        )

        output = result.stdout
        # Optionally parse output here, e.g. SSID, BSSID, RSSI, etc.
        return output

    def get_wifi_verbose_info(self):
        result = subprocess.run(
            f'"{self.adb}" -s {self.name} shell cmd wifi status',
            shell=True, text=True, capture_output=True
        )

        return result.stdout

    def get_device_summary(self) -> None:
        logger.info(f"Device Model: {self.get_device_model()}")
        logger.info(f"Manufacturer: {self.get_manufacturer()}")
        logger.info(f"Android Version: {self.get_android_version()}")
        logger.info(f"SDK Version: {self.get_sdk_version()}")
        logger.info(f"Battery Info: {self.get_battery_info()}")
        logger.info(f"Total Storage: {self.get_total_storage()}")
        logger.info(f"WLAN IP: {self.wlan_ip(self.name)}")

    def get_info(self) -> None:
        super().get_info(self.name)
    
    def screenshot(self) -> Image.Image:
        return super().screenshot(self.name)

    def screenInput(self, x: int, y: int) -> None:
        x_scaled = x * self.abs_res_scalar_x
        y_scaled = y * self.abs_res_scalar_y
        super().screenInput(self.name, x_scaled, y_scaled)

    def screenSwipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        x1_scaled = x1 * self.abs_res_scalar_x
        y1_scaled = y1 * self.abs_res_scalar_y
        x2_scaled = x2 * self.abs_res_scalar_x
        y2_scaled = y2 * self.abs_res_scalar_y
        super().screenSwipe(self.name, x1_scaled, y1_scaled, x2_scaled, y2_scaled)

    def text_input(self, text: str) -> None:
        super().text_input(self.name, text)

    def keyevent_input(self, code: Union[int, str]) -> None:
        super().keyevent_input(self.name, code)
        
    def resolution(self) -> List[int]:
        return super().resolution(self.name)

    def orientation(self) -> str:
        return super().orientation(self.name)

    def currentfocus(self) -> str:
        return super().currentfocus(self.name)

    def app_resolution(self) -> List[float]:
        return super().app_resolution(self.name)

    def wlan_ip(self, device_identifier: str) -> str:
        return super().wlan_ip(self.name)

class Emulator(BaseDevice):
    def __init__(
        self,
        port: int = 5554,
        devices: int = 0,
        emulator: bool = True,
        name: Optional[str] = None,
        adb_path: Optional[str] = None
    ) -> None:
        super().__init__(adb_path)
        self.port = str(port)
        self.devices = self.find_devices()
        self.emulator = emulator
        self.name = name
        
        if not emulator:
            raise SystemError("Only emulator devices are supported")
        
        self._connect_emulators()
        self.identifier = f"emulator-{self.port}"
        
        # Original resolution scaling logic
        emu_res = self.resolution()
        app_res = self.app_resolution()
        self.ORIENTATION = self.orientation()
        self._currentapp = self.currentfocus()

        self.abs_res_scalar_x = emu_res[0] / self.BASE_RESOLUTION_EMU[0]
        self.abs_res_scalar_y = emu_res[1] / self.BASE_RESOLUTION_EMU[1]
        self.rel_res_scalar_x = app_res[0] / self.BASE_RESOLUTION_EMU[0]
        self.rel_res_scalar_y = app_res[1] / self.BASE_RESOLUTION_EMU[1]
        
        self.get_info()

    def find_devices(self) -> List[str]:
        devices_output = subprocess.run(
            f'"{self.adb}" devices',
            shell=True, capture_output=True, text=True
        )

        devices = devices_output.stdout.split()
        devices = devices[4:]
        devices = [i for i in devices if i != 'device' and 'phone' not in i]

        if not devices:
            raise ConnectionError("No emulator devices found")
        else:
            print(f'Found {len(devices)} emulator devices')
            for i in devices:
                print(f'Port: {i[-4:]} with name: {i}')
        return len(devices)

    def _connect_emulators(self) -> None:
        ports = self._generate_ports()
        print(ports)

        if self.port not in ports:
            if self.devices == -1:
                self.port = str(self.port)
            else:
                logger.warning(f"Port {self.port} not found, defaulting to 5554")
                self.port = '5554'
        
        subprocess.run(
            f'"{self.adb}" connect emulator-{self.port}',
            shell=True, check=True
        )

    def _generate_ports(self) -> List[int]:
        #leave blank for auto port generation
        if self.devices == -1:
            return [str(self.port)]
        if self.devices == 1:
            return ['5554']
        if self.devices == 2:
            return ['5554', '5556']
        return [str(5554 + 2 * i) for i in range(self.devices)]

    # All original Emulator methods maintained
    def get_info(self) -> None:
        super().get_info(self.identifier)
    
    def screenshot(self) -> Image.Image:
        return super().screenshot(self.identifier)

    def screenInput(self, x: int, y: int) -> None:
        x_scaled = x * self.abs_res_scalar_x
        y_scaled = y * self.abs_res_scalar_y
        super().screenInput(self.identifier, x_scaled, y_scaled)

    def screenSwipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        x1_scaled = x1 * self.abs_res_scalar_x
        y1_scaled = y1 * self.abs_res_scalar_y
        x2_scaled = x2 * self.abs_res_scalar_x
        y2_scaled = y2 * self.abs_res_scalar_y
        super().screenSwipe(self.identifier, x1_scaled, y1_scaled, x2_scaled, y2_scaled)

    def text_input(self, text: str) -> None:
        super().text_input(self.identifier, text)

    def keyevent_input(self, code: Union[int, str]) -> None:
        super().keyevent_input(self.identifier, code)

    def resolution(self) -> List[int]:
        return super().resolution(self.identifier)

    def orientation(self) -> str:
        return super().orientation(self.identifier)

    def currentfocus(self) -> str:
        return super().currentfocus(self.identifier)

    def app_resolution(self) -> List[float]:
        return super().app_resolution(self.identifier)

    def wlan_ip(self) -> str:  # No device_identifier parameter here
        try:
            # First try eth0 which emulators often use
            result = subprocess.run(
                f'"{self.adb}" -s {self.identifier} shell ip addr show eth0',
                shell=True,
                text=True,
                capture_output=True
            )
            if result.returncode == 0:
                lines = [line.split() for line in result.stdout.splitlines() if 'inet' in line]
                if lines:
                    return lines[0][1].split('/')[0]
            
            # Fall back to localhost
            return "127.0.0.1"
        except Exception:
            return "127.0.0.1"

    def get_info(self) -> None:
        logger.info(f"\nInfo for emulator: {self.identifier}")
        subprocess.run(f'"{self.adb}" -s {self.identifier} shell wm size', check=True, shell=True)
        logger.info(f"App in focus: {self._currentapp}")
        logger.info(f"Orientation: {self.ORIENTATION}")
        
        # Call our parameter-less wlan_ip()
        logger.info(f"wlan ip: {self.wlan_ip()}")
        
        subprocess.run(f'"{self.adb}" -s {self.identifier} get-serialno', shell=True)

    def kill_connection(self) -> None:
        super().kill_connection(self.identifier)

class ImageOcr:
    def __init__(self, im: Image.Image) -> None:
        self.im = im
        self.BASE_RESOLUTION_EMU = [1920, 1080]
        self.BASE_RESOLUTION_PHN = [2400, 1080]
        
        # Ensure Tesseract is configured correctly
        current_dir = os.getcwd()
        tesseract_path = self._find_executable('tesseract.exe' if os.name == 'nt' else 'tesseract', current_dir)
        if not tesseract_path:
            raise FileNotFoundError("Tesseract OCR not found")
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

    def crop_image(self, x1: int, y1: int, x2: int, y2: int, res_scalar_x: float, res_scalar_y: float) -> Image.Image:
        x1_scaled = x1 * res_scalar_x
        y1_scaled = y1 * res_scalar_y
        x2_scaled = x2 * res_scalar_x
        y2_scaled = y2 * res_scalar_y
        return self.im.crop((x1_scaled, y1_scaled, x2_scaled, y2_scaled))
    
    def _find_executable(self, filename: str, search_path: str) -> Optional[str]:
        """Locate the Tesseract executable"""
        for root, dirs, files in os.walk(search_path):
            if filename in files:
                return os.path.join(root, filename)
        return None

    def preprocess_image(self) -> Image.Image:
        """Preprocess the image for OCR (grayscale, binarize, and denoise)"""
        # Convert to grayscale
        im = self.im.convert('L')

        return im

    def get_text(self) -> str:
        """Get OCR text from the image (preprocessed for best accuracy)"""
        preprocessed_im = self.im

        # Perform OCR using Tesseract
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(preprocessed_im,config=custom_config)
        return text.split()

    def match_all_phrases(self,words_data, phrase_words, y_tolerance=10):
        matches = []
        i = 0
        matched = []

        for w in words_data:
            if w['text'] == phrase_words[i]:
                if matched and abs(w['top'] - matched[-1]['top']) > y_tolerance:
                    matched = []
                    i = 0
                    continue
                matched.append(w)
                i += 1
                if i == len(phrase_words):
                    matches.append(matched)
                    matched = []  # reset to allow next match
                    i = 0
            elif w['text'] == phrase_words[0]:
                matched = [w]
                i = 1
            else:
                matched = []
                i = 0
        return matches


    def locate_text(self, target_text: str):
        start = time.time()

        allowed_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789,. '

        """Locate specific text and save image with bounding boxes"""
        # Convert the PIL image to OpenCV format (NumPy array)
        open_cv_image = cv2.cvtColor(np.array(self.im), cv2.COLOR_RGB2BGR)

        # Convert the image to grayscale (helps in text detection)
        gray_image = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)

        # Optional: Apply thresholding to make text clearer
        _, threshold_image = cv2.threshold(gray_image, 150, 255, cv2.THRESH_BINARY)

        # Perform OCR using Tesseract
        custom_config = r'--oem 1 --psm 3'
        detection_result = pytesseract.image_to_data(threshold_image, output_type=pytesseract.Output.DICT, config=custom_config)

        words_data = []
        for i in range(len(detection_result['text'])):
            word = detection_result['text'][i].strip().lower()
            if word:
                # Filter out single-character words and words that only consist of non-alphanumeric characters
                if len(word) > 1 and re.search(r'[a-zA-Z0-9]', word):
                    # Filter out unwanted characters (only allow alphanumeric and basic punctuation)
                    word = ''.join(c for c in word if c in allowed_chars)

                    # Only keep the word if it has at least one alphanumeric character
                    if word and re.search(r'[a-zA-Z0-9]', word):
                        x = detection_result['left'][i]
                        y = detection_result['top'][i]
                        w = detection_result['width'][i]
                        h = detection_result['height'][i]
                        words_data.append({
                            'text': word,
                            'left': x,
                            'top': y,
                            'width': w,
                            'height': h
                        })

        targets = []
        if isinstance(target_text, str):
            phrases = [target_text.lower()]
        else:
            phrases = [p.lower() for p in target_text]

        for phrase in phrases:
            phrase_words = phrase.split()
            all_matches = self.match_all_phrases(words_data, phrase_words)

            for match in all_matches:
                # Just append the coordinates to targets, no drawing bounding boxes
                x1 = match[0]['left']
                y1 = match[0]['top']
                x2 = match[-1]['left'] + match[-1]['width']
                y2 = match[-1]['top'] + match[-1]['height']

                # Adding padding/margin for clarity
                padding = 5
                x1, y1, x2, y2 = x1 - padding, y1 - padding, x2 + padding, y2 + padding

                # Draw bounding box on the image (around valid words)
                cv2.rectangle(open_cv_image, (x1, y1), (x2, y2), (0, 255, 0), 2)  # green box
                print(f"Found phrase '{target_text}' at: (x1: {x1}, y1: {y1}, x2: {x2}, y2: {y2})")
                targets.append([x1, y1, x2, y2])

            if not all_matches:
                print(f"Phrase '{target_text}' not found.")

        debug_image = open_cv_image.copy()  # make a copy so your final result isn't overwritten

        # Draw bounding boxes for all valid words (after filtering out unwanted words)
        for i in range(len(detection_result['text'])):
            word = detection_result['text'][i].strip()
            if word:
                x = detection_result['left'][i]
                y = detection_result['top'][i]
                w = detection_result['width'][i]
                h = detection_result['height'][i]

                # Draw bounding boxes for valid words
                if len(word) > 1 and re.search(r'[a-zA-Z0-9]', word):
                    cv2.rectangle(debug_image, (x, y), (x + w, y + h), (255, 0, 0), 2)  # blue boxes
                    cv2.putText(debug_image, word, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

        # Save the debug image for review
        cv2.imwrite("detected_text_filtered.jpg", debug_image)
        print(f'OCR time: {time.time() - start}')
        return targets
