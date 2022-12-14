import subprocess as sp, shlex
import time
import asyncio
from contextlib import suppress


def current_milli_time():
    return round(time.time() * 1000)

async def run3(cmd):

    rc = 0

    while rc is not None:
        # print("run3 new loop", cmd)
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)

        previous_time = 0
        interval = 100
        program_count = 0
        program_max_count = 25
        failed = False

        i = 0

        while proc.returncode is None and not failed:
            current_time = current_milli_time()
            # print("run3 inner loop", cmd, i)
     
            line = await proc.stdout.readline()
            if line != b'':
                # print(proc.pid, line)
                pass
            else:
                break

            if program_count >= program_max_count:
                failed = True
                break

            if i > 1000:
                failed = True
                break

            if (current_time - previous_time) >= interval:
                program_count+=1

            previous_time = current_time
            i+=1

        # print(failed)
        if failed:
            proc.kill()
            proc.terminate()

async def main():

    await asyncio.gather(
        run3("python3 /home/pi/camera/cameracore2.py"),
        run3("python3 /home/pi/controls-thread/bmdproxy.py"),
        run3("./home/pi/mmal_render_ui/render"),
        # run3("sudo -E python3 /home/pi/audio_rec.py"),
        run3("watch -n 6 /home/pi/clear_cache.sh"),
        # CineMate scripts
        run3("python3 /home/pi/cinemate/manual_controls.py"),
        run3("python3 /home/pi/cinemate/rec_signal.py"),
        run3("python3 /home/pi/cinemate/metadata.py"))
        
asyncio.run(main())
        






