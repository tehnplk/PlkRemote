import dxcam
import numpy as np
from turbojpeg import TurboJPEG

def test():
    try:
        camera = dxcam.create()
        print("dxcam initialized")
        frame = camera.grab()
        if frame is not None:
            print(f"Captured frame shape: {frame.shape}")
        
        try:
            jpeg = TurboJPEG()
            print("TurboJPEG initialized")
        except Exception as e:
            print(f"TurboJPEG failed to initialize: {e}. You might need to install libturbojpeg.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
