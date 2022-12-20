# from pyv4l2.control import Control
from fractions import Fraction 
import subprocess as sp, shlex

ctrls = {
    "vertical_blanking": 0x009e0901,
    "horizontal_blanking": 0x009e0902,
    "analogue_gain": 0x009e0903,
    "pixel_rate": 0x009f0902,
    "exposure": 0x00980911,
    "horizontal_flip": 0x00980914,
    "vertical_flip": 0x00980915,
    "digital_gain": 0x009f0905
}

ctrls = {
    "vertical_blanking": "vertical_blanking",
    "horizontal_blanking": "horizontal_blanking",
    "analogue_gain":"analogue_gain",
    "pixel_rate": "pixel_rate",
    "exposure": "exposure",
    "horizontal_flip":"horizontal_flip",
    "vertical_flip": "vertical_flip",
    "digital_gain": "digital_gain",
    "red_pixel_value":"red_pixel_value",
    "green_red_pixel_value":"green_red_pixel_value",
    "blue_pixel_value":"blue_pixel_value",
    "green_blue_pixel_value":"green_blue_pixel_value"
}
            
class Control:
    def __init__(self, device):
        self.device = device

    def get_control_value(self, control):
        r = sp.check_output(['v4l2-ctl', '-d', self.device, '--get-ctrl', str(control)])
        res = int(''.join(filter(str.isdigit, str(r))))
        return res

    def set_control_value(self, control, value):
        sp.check_call(['v4l2-ctl', '-d', self.device, '--set-ctrl', str(control)+"="+str(value)])

    def get_resolution(self):
        resolution = (0,0)
        out = sp.check_output(['v4l2-ctl', '-d', self.device, '--log-status'])
        for line in out.splitlines():
            l = line.decode("UTF-8")
            if "V4L2 width/height:" in l:
                res = l.split(":")[-1]
                dim = res.split("x")
                resolution = (int(dim[0]),int(dim[1]))
        return resolution
    
class CameraParameters:
    def __init__(self, type):
        self.type = type
        self.controls = Control("/dev/video0")
        # self.get()

    def __repr__(self):
        return self.value

    def __str__(self):
        return str(self.value)

    def __convert__(self, value=None):
        res = self.controls.get_resolution()
        width = res[0]
        height = res[1]

        if self.type == "ISO":

            if not value:
                raw = self.controls.get_control_value(ctrls["analogue_gain"])
                iso = (1024.0 / (1024.0 - raw)) * 100
                #legal = [100,125,200,250,320,400,500,640,800,1000,1250,1600,2000,2500,3200]
                #return min(legal, key=lambda x:abs(x-iso))
                return iso

            else:

                raw = int(-((1024 / value * 100) - 1024))
                self.controls.set_control_value(ctrls["analogue_gain"], raw)

        elif self.type == "SHUTTER":
            if not value:
                
                v_blank = self.controls.get_control_value("vertical_blanking")
                w = float(res[0])
                h = float(res[1])
                px_rate = 840000000.0
                hz_blank = 10712.0
                fps = int(px_rate / ((w+hz_blank) * (h+v_blank)))
                
                w = float(res[0])
                exp = float(self.controls.get_control_value("exposure"))
                px_rate = 840000000.0
                hz_blank = 10712.0
                ex_ms = ((w+hz_blank) / px_rate) * exp
                speed = int(1/ex_ms)
                angle = int(((float(fps) * 360.0) / float(speed)))
                return speed, angle, ex_ms
                
            else:
                v_blank = self.controls.get_control_value("vertical_blanking")
                w = float(res[0])
                h = float(res[1])
                px_rate = 840000000.0
                hz_blank = 10712.0
                fps = int(px_rate / ((w+hz_blank) * (h+v_blank)))
                shutter_speed = (value/360)/fps
                exposure = round(shutter_speed/0.000015184645286)
                self.controls.set_control_value(ctrls["exposure"],int(exposure))
                
        elif self.type == "FPS":
            if not value:
                v_blank = self.controls.get_control_value("vertical_blanking")
                w = float(res[0])
                h = float(res[1])
                px_rate = 840000000.0
                hz_blank = 10712.0
                fps = int(px_rate / ((w+hz_blank) * (h+v_blank)))
                return fps
            else:
                v_blank = self.controls.get_control_value("vertical_blanking")
                w = float(res[0])
                h = float(res[1])
                px_rate = 840000000.0
                hz_blank = 10712.0
                fps = int(px_rate / ((w+hz_blank) * (h+v_blank)))
                
                hz_blnk = self.controls.get_control_value(ctrls["horizontal_blanking"])
                nvt_blnk = (( (1/value) * px_rate ) / (width + hz_blnk)) - height
                if nvt_blnk < 0:
                    nvt_blnk = 0
                self.controls.set_control_value(ctrls["vertical_blanking"], int(nvt_blnk))

        elif self.type == "RESOLUTION":
            if not value:
                pass

            else: 
                if value == 1:
                    w = 2028
                    h = 1080
                
                if value == 2:
                    w = 2028
                    h = 1520
                    
                self.controls.set_control_value(ctrls["green_red_pixel_value"],int(w))
                self.controls.set_control_value(ctrls["green_blue_pixel_value"],int(h))
                res = self.controls.get_resolution()
                width = res[0]
                height = res[1]
            
                return width, height

    def get(self):
        self.value = self.__convert__()
        return self.value

    def set(self, value):
        self.__convert__(value=value)
        self.value = value
        return self.value
    