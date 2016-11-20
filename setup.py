from setuptools import setup, find_packages

setup(name='ampioip',
      version='0.0.1',
      description='A Python Ampio IP client implementation',
      url='http://github.com/kstaniek/ampioip',
      author='Klaudiusz Staniek',
      author_email='kstaniek@gmail.com',
      license='MIT',
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Intended Audience :: Developers',
          'Topic :: System :: Hardware :: Hardware Drivers',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.4',
          'Programming Language :: Python :: 3.5'
      ],
      packages=find_packages(),
      keywords='ampio  automation',
      zip_safe=False)
