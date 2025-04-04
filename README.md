ADB Device Control Library
=========================

A Python library for controlling Android devices via ADB with features for both physical devices and emulators.

Key Features:
- Device management for phones and emulators
- Screen interaction (tap, swipe, text input)
- Screenshot capture and OCR text recognition
- Automatic resolution scaling
- Device information retrieval

Requirements:
- Python 3.7+
- ADB installed and configured
- Tesseract OCR (for text recognition)

Installation:
1. Install system requirements:
   - ADB tools
   - Tesseract OCR
2. Install Python dependencies:
   pip install pillow pytesseract

Basic Usage:
from adb_control import Phone, Emulator

# Connect to device
device = Phone(name="device_serial")  # or Emulator(port=5554)

# Take screenshot
screenshot = device.screenshot()

# Tap screen
device.screenInput(x=500, y=500)

See documentation.txt for complete API reference.

License: Apache 2.0
