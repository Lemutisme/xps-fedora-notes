#!/usr/bin/python3
"""Install the selected artifacts of an already reviewed and compiled Howdy build.

This helper does not build dependencies, enroll faces, or modify PAM services.
Use only with a trusted build directory; run with sudo, not python -O.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build_dir', type=Path)
    parser.add_argument('model_dir', type=Path)
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run with sudo')
    if Path('/usr/lib64/security/pam_howdy.so').exists() or Path('/etc/howdy/config.ini').exists():
        parser.error('An existing installation needs manual review; refusing to overwrite it')
    if not Path('/opt/howdy/venv/bin/python').is_file():
        parser.error('Create the isolated environment first')

    manifest = json.loads((args.build_dir / 'meson-info/intro-installed.json').read_text())
    pairs = []
    for source, destination in manifest.items():
        if not isinstance(destination, str):
            continue
        target = Path(destination)
        if '..' in target.parts:
            parser.error('Unexpected path in build manifest')
        if destination.startswith('/usr/local/lib64/howdy/') or destination in (
            '/usr/lib64/security/pam_howdy.so', '/usr/local/bin/howdy'
        ):
            source = Path(source)
            if not source.is_file():
                parser.error(f'Missing build artifact: {source}')
            if target.exists():
                parser.error(f'Refusing to overwrite existing artifact: {target}')
            pairs.append((source, target))
    destinations = {str(target) for _, target in pairs}
    required = {'/usr/lib64/security/pam_howdy.so', '/usr/local/bin/howdy',
                '/usr/local/lib64/howdy/compare.py', '/usr/local/lib64/howdy/paths.py'}
    if not required <= destinations:
        parser.error('Build layout differs from the documented Meson configuration')
    models = ['shape_predictor_5_face_landmarks.dat',
              'dlib_face_recognition_resnet_model_v1.dat', 'mmod_human_face_detector.dat']
    for name in models:
        if not (args.model_dir / name).is_file():
            parser.error(f'Missing pretrained model: {name}')
    if not args.config.is_file():
        parser.error('Missing reviewed configuration')

    for source, target in pairs:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o755 if str(target) in required and
                     (target.suffix == '.so' or target.name == 'howdy') else 0o644)
    model_target = Path('/usr/local/share/howdy/dlib-data')
    model_target.mkdir(parents=True, exist_ok=True)
    for name in models:
        shutil.copyfile(args.model_dir / name, model_target / name)
        (model_target / name).chmod(0o644)
    Path('/etc/howdy/models').mkdir(parents=True, mode=0o700, exist_ok=True)
    Path('/etc/howdy/models').chmod(0o700)
    Path('/var/log/howdy').mkdir(mode=0o700, exist_ok=True)
    shutil.copyfile(args.config, '/etc/howdy/config.ini')
    Path('/etc/howdy/config.ini').chmod(0o644)
    subprocess.run(['restorecon', '-RF', '/opt/howdy', '/etc/howdy',
                    '/usr/local/lib64/howdy', '/usr/local/share/howdy',
                    '/usr/lib64/security/pam_howdy.so', '/usr/local/bin/howdy'], check=True)
    print('Artifacts installed. Enroll and verify before enabling GDM authentication.')


if __name__ == '__main__':
    main()
