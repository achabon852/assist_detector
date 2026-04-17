from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='assist_detector',
            executable='assist_detector_node',
            name='assist_detector',
            output='screen'
        )
    ])
