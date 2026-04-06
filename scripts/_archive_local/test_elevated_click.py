import sys, ctypes, time, os, traceback

LOG = r'c:\temp\elevated_log.txt'
os.makedirs(r'c:\temp', exist_ok=True)

with open(LOG, 'w') as f:
    f.write("start\n")

try:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    with open(LOG, 'a') as f:
        f.write("imports...\n")

    import pyautogui
    pyautogui.FAILSAFE = False
    from orchestrator.local_automation.screen_utils import get_window_rect, set_window_rect

    u = ctypes.windll.user32

    with open(LOG, 'a') as f:
        f.write("finding window...\n")

    results = []
    def cb(h, _):
        if not u.IsWindowVisible(h):
            return True
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(h, buf, 256)
        if '481.300' in buf.value:
            results.append((h, buf.value))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    u.EnumWindows(WNDENUMPROC(cb), 0)

    with open(LOG, 'a') as f:
        f.write("windows found: %d\n" % len(results))
        for h, t in results:
            f.write("  hwnd=%d title=%s\n" % (h, t))

    if not results:
        with open(LOG, 'a') as f:
            f.write("NO WINDOW FOUND\n")
        sys.exit(1)

    hwnd = results[0][0]
    set_window_rect(hwnd, 0, 0, 1260, 950)
    time.sleep(0.3)
    u.SetForegroundWindow(hwnd)
    time.sleep(0.5)

    rect = get_window_rect(hwnd)
    left, top = rect[0], rect[1]

    with open(LOG, 'a') as f:
        f.write("clicking at (%d, %d)\n" % (left + 385, top + 612))

    pyautogui.tripleClick(left + 385, top + 612)
    time.sleep(0.5)
    pyautogui.typewrite('10', interval=0.05)
    time.sleep(0.5)

    from PIL import ImageGrab
    import numpy as np, cv2
    img = ImageGrab.grab(bbox=(left, top, left+1260, top+950))
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    cv2.imwrite(r'c:\temp\elevated_test.png', arr)

    with open(LOG, 'a') as f:
        f.write("DONE\n")

except Exception as e:
    with open(LOG, 'a') as f:
        f.write("ERROR: %s\n%s\n" % (e, traceback.format_exc()))
