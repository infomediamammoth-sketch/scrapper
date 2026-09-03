import os
import subprocess
from PIL import Image, ImageDraw

def create_ico():
    # 256x256 Canvas, transparent background
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Magnifier Handle (diagonal rounded thick stroke)
    draw.line([(50, 206), (110, 146)], fill=(37, 99, 235), width=28, joint="round")
    draw.line([(50, 206), (70, 186)], fill=(29, 78, 216), width=28, joint="round")

    # 2. Outer Ring
    draw.ellipse([(95, 31), (225, 161)], fill=(248, 250, 252), outline=(37, 99, 235), width=16)

    # 3. Inner glass lens
    draw.ellipse([(111, 47), (209, 145)], fill=(219, 234, 254))

    # 4. Glass reflection highlights
    draw.arc([(125, 61), (195, 131)], start=200, end=300, fill=(255, 255, 255), width=8)

    # Save multi-size windows icon
    icon_path = os.path.abspath("magnifier.ico")
    img.save(icon_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
    print(f"Generated icon: {icon_path}")
    return icon_path

def create_shortcut(icon_path):
    desktop = os.path.expanduser("~/Desktop")
    shortcut_path = os.path.join(desktop, "Google Business Scraper.lnk")
    target_path = os.path.abspath("run_app.bat")
    working_dir = os.path.abspath(".")
    
    ps_script = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
    $Shortcut.TargetPath = "{target_path}"
    $Shortcut.WorkingDirectory = "{working_dir}"
    $Shortcut.IconLocation = "{icon_path}"
    $Shortcut.WindowStyle = 7
    $Shortcut.Save()
    """
    
    # Run powershell script
    res = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
    if res.returncode == 0:
        print(f"Desktop shortcut created at: {shortcut_path}")
    else:
        print(f"Error creating shortcut: {res.stderr}")

if __name__ == "__main__":
    icon_p = create_ico()
    create_shortcut(icon_p)
