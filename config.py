import os
from flask import Flask

class Config:
    """Base configuration"""
    SECRET_KEY = 'efams_secret'
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = ''
    MYSQL_DB = 'efams_db'