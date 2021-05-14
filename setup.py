from setuptools import setup, find_packages


def dependencies(imported_file):
    """ __Doc__ Handles dependencies """
    with open(imported_file) as file:
        return file.read().splitlines()


setup(name="proxyrotate", description="proxy rotation script using haproxy",
      version="1.0.0", install_requires=dependencies("requirements.txt"), packages=find_packages(), entry_points={'console_scripts': ['proxyrotate = proxyrotate.update:main']})
