#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ruff: noqa: F821
# (ruff don't see read variables from release.py)

from setuptools import find_namespace_packages, setup
from os.path import join, dirname


exec(open(join(dirname(__file__), 'odoo', 'release.py'), 'rb').read())  # Load release variables
lib_name = 'odoo'

setup(
    name='odoo',
    version=version,
    description=description,
    long_description=long_desc,
    url=url,
    author=author,
    author_email=author_email,
    classifiers=[c for c in classifiers.split('\n') if c],
    license=license,
    scripts=['setup/odoo'],
    packages=find_namespace_packages(),
    package_dir={'%s' % lib_name: 'odoo'},
    include_package_data=True,
    install_requires=[
        'asn1crypto', 'babel >= 1.0', 'cbor2', 'chardet', 'cryptography',
        'docutils', 'geoip2', 'gevent', 'greenlet', 'h11', 'idna', 'Jinja2',
        'lxml', 'lxml_html_clean', 'libsass', 'MarkupSafe', 'num2words',
        'ofxparse', 'openpyxl', 'passlib', 'pillow', 'polib', 'psutil',
        'psycopg2 >= 2.2', 'pyopenssl', 'pypdf', 'pyserial',
        'python-dateutil', 'python-stdnum', 'pyusb >= 1.0.0b1', 'qrcode',
        'reportlab', 'rjsmin', 'requests', 'urllib3', 'vobject', 'werkzeug',
        'xlrd', 'xlsxwriter', 'zeep',
    ],
    python_requires='>=' + ".".join(map(str, MIN_PY_VERSION)),
    extras_require={'ldap': ['python-ldap']},
    tests_require=['freezegun'],
)
