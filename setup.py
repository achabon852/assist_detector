from setuptools import setup
from glob import glob

package_name = 'assist_detector'

setup(
    name=package_name,
    version='0.1.7',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/scripts', glob('scripts/*.sh')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='user',
    maintainer_email='user@example.com',
    description='Japanese multi-person emotion overlay detector using DeepFace with stable OpenCV face detection',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'assist_detector_node = assist_detector.node:main',
        ],
    },
)
