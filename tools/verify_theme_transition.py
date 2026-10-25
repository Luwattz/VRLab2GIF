"""Verify displayed theme layers on all pages, then measure real mainloop frames."""
import argparse, ctypes, json, statistics, sys, time
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageChops, ImageGrab, ImageStat
from tkinterdnd2 import TkinterDnD
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vrlab2gif.app import GifCreatorApp
from vrlab2gif.appearance import PALETTES, enable_dpi_awareness
from vrlab2gif.theme_scene import capture_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    enable_dpi_awareness()
    root = TkinterDnD.Tk()
    app = GifCreatorApp(root)
    root.attributes('-topmost', True)
    root.geometry('+40+40'); root.update()
    fade = app.appearance.transition
    fade.motion_enabled = app.theme_switch.motion_enabled = app.navigation.motion_enabled = True
    report = {'size': [root.winfo_width(), root.winfo_height()], 'frames': [],
              'preparations': [], 'endings': [], 'timings': []}
    user, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

    def displayed_frame():
        bounds = wintypes.RECT()
        assert user.GetWindowRect(int(root.wm_frame(), 0), ctypes.byref(bounds))
        dwm.DwmFlush()
        return (ImageGrab.grab(bbox=(bounds.left, bounds.top, bounds.right, bounds.bottom),
                               include_layered_windows=True), bounds)

    def check_bottom(picture, bounds, color):
        rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        x = root.winfo_rootx()-bounds.left+root.winfo_width()//2
        bottom = root.winfo_rooty()-bounds.top+root.winfo_height()
        pixels = [picture.getpixel((x, bottom-distance))
                  for distance in (1, 2, app.appearance.px(6))]
        error = max(abs(a-b) for pixel in pixels for a,b in zip(pixel, rgb))
        assert error <= 2, ('bottom strip', pixels, rgb)
        return error

    try:
        for page in ('settings', 'filters', 'logs'):
            app.navigation.select(page, animate=False); root.update()
            for target in ('light', 'dark'):
                source = capture_client(root)
                source_background = app.appearance.colors.background
                captures = []
                def capture(window):
                    image = capture_client(window)
                    captures.append(image)
                    if len(captures) == 2:
                        # Inspect the screen while target widgets are painted
                        # behind the initial source shield, before any fade.
                        picture, bounds = displayed_frame()
                        error = check_bottom(picture, bounds, source_background)
                        picture.save(output/f'{page}-{target}-prepare.png')
                        report['preparations'].append({'page': page, 'toward': target,
                                                       'bottom_error': error})
                    return image
                with patch('vrlab2gif.theme_scene.capture_client', side_effect=capture):
                    app.theme_switch.select(target)
                fade.cancel()
                assert fade.scene.active, fade.scene.last_error
                destination = captures[-1]
                # Verify actual endpoint colors as well as their blend: a
                # layer accidentally captured in both endpoints can otherwise
                # make a frozen body pass the pixel comparison below.
                for image, color in ((source, source_background),
                                     (destination, PALETTES[target].background)):
                    expected_color = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
                    assert image.getpixel((0, image.height//2)) == expected_color
                top = fade.scene.top
                box = (0, top, source.width, source.height)
                dark, light = ((source.crop(box), destination.crop(box)) if target == 'light'
                               else (destination.crop(box), source.crop(box)))
                for amount in (0, .2, .4, .6, .8, 1):
                    # Inspect the DWM submission before Tk drains its paint
                    # queue: waiting for idle used to hide header/body skew.
                    fade.render(amount)
                    bounds = wintypes.RECT()
                    assert user.GetWindowRect(int(root.wm_frame(), 0), ctypes.byref(bounds))
                    dwm.DwmFlush()
                    # Default ImageGrab skips layered windows: that would inspect
                    # hidden backing controls instead of the displayed transition.
                    picture = ImageGrab.grab(bbox=(bounds.left, bounds.top, bounds.right, bounds.bottom),
                                             include_layered_windows=True)
                    x, y = root.winfo_rootx()-bounds.left, root.winfo_rooty()-bounds.top
                    p = app.appearance.px
                    points = ((x+p(8), app.heading.winfo_rooty()-bounds.top+p(4)),
                              (x+p(8), y+source.height//2),
                              (x+source.width//2, y+source.height-1),
                              (x+source.width//2, y+source.height-2),
                              (x+source.width//2, y+source.height-p(6)))
                    backgrounds = [picture.getpixel(point) for point in points]
                    skew = max(abs(a-b) for color in backgrounds[1:]
                               for a, b in zip(color, backgrounds[0]))
                    assert skew <= 2, (page, target, amount, 'background skew', backgrounds)
                    actual = picture.crop((x, y+top, x+source.width, y+source.height))
                    expected = Image.blend(dark, light, round(amount*255)/255)
                    difference = ImageChops.difference(actual, expected)
                    mean = max(ImageStat.Stat(difference).mean)
                    histogram = difference.histogram()
                    wrong = sum(sum(histogram[c*256+4:(c+1)*256]) for c in range(3))
                    fraction = wrong/(actual.width*actual.height*3)
                    picture.save(output/f'{page}-{target}-{round(amount*100):03d}.png')
                    if mean >= 1.2 or fraction >= .003:
                        actual.save(output/'actual.png')
                        expected.save(output/'expected.png')
                        print('flat colors', actual.getpixel((50, 50)), expected.getpixel((50, 50)))
                    # Allow native rounding/subpixel edges, reject large areas
                    # of independently painted controls at a different phase.
                    assert mean < 1.2 and fraction < .003, (page, target, amount, mean, fraction)
                    if getattr(root, '_vrlab_caption_colors_supported', False):
                        bg = tuple(int(app.appearance.colors.background[i:i+2], 16) for i in (1, 3, 5))
                        pixel = picture.getpixel((picture.width//2, y//2))[:3]
                        assert max(abs(a-b) for a, b in zip(pixel, bg)) <= 2, (pixel, bg)
                    picture.save(output/f'{page}-{target}-{round(amount*100):03d}.png')
                    report['frames'].append({'page': page, 'toward': target, 'alpha': amount,
                                             'background_skew': skew,
                                             'mean_error': round(mean, 4), 'pixels_over_3': round(fraction, 6)})
                    root.update_idletasks()
                fade.finish()
                root.update_idletasks()
                picture, bounds = displayed_frame()
                error = check_bottom(picture, bounds, PALETTES[target].background)
                picture.save(output/f'{page}-{target}-finished.png')
                report['endings'].append({'page': page, 'toward': target, 'bottom_error': error})

        pending = None
        for name, control in (('theme', app.theme_switch), ('page', app.navigation), ('body', fade)):
            original = control._tick
            def tick(name=name, original=original):
                if pending is not None: pending[name].append(time.perf_counter())
                original()
            control._tick = tick
        operations = [('theme-light', lambda: app.theme_switch.select('light')),
                      ('theme-dark', lambda: app.theme_switch.select('dark')),
                      ('page-settings', lambda: app.navigation.select('settings')),
                      ('page-filters', lambda: app.navigation.select('filters')),
                      ('page-logs', lambda: app.navigation.select('logs'))]
        def advance(index=0):
            nonlocal pending
            if pending is not None:
                item = {'operation': pending['operation'], 'setup_ms': pending['setup_ms']}
                for key in ('theme', 'page', 'body'):
                    stamps = pending[key]
                    if len(stamps) > 1:
                        gaps = sorted((b-a)*1000 for a, b in zip(stamps, stamps[1:]))
                        item[key] = {'frames': len(stamps), 'p50_ms': round(statistics.median(gaps), 2),
                                     'p95_ms': round(gaps[int(len(gaps)*.95)], 2), 'max_ms': round(max(gaps), 2)}
                report['timings'].append(item)
            if index == len(operations):
                pending = None; root.quit(); return
            name, operation = operations[index]
            pending = {'operation': name, 'theme': [], 'page': [], 'body': []}
            start = time.perf_counter(); operation()
            pending['setup_ms'] = round((time.perf_counter()-start)*1000, 2)
            root.after(900, lambda: advance(index+1))
        root.after(200, advance); root.mainloop()
        assert fade.timer_id is None and not fade.scene.active
        assert not any(c.timing.precise for c in (fade, app.theme_switch, app.navigation))
        (output/'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({'screen_frames': len(report['frames']),
                          'preparation_frames': len(report['preparations']),
                          'finished_frames': len(report['endings']), 'timings': report['timings']}))
    finally:
        app.on_close()


if __name__ == '__main__':
    main()
