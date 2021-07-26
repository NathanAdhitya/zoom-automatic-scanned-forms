import base64
from time import perf_counter
import time
import os

from Crypto.Cipher import AES
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium_stealth import stealth

import string
import random

import sys
import signal
import redis

from dotenv import load_dotenv
load_dotenv()

# 128, 192, or 256 bits
key = os.environ.get("KEY")
assert(len(key) in {16, 24, 32})
key = str.encode(key)


def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


script_id = id_generator(8)
print("Running as script id:", script_id)

r = redis.Redis(host='localhost', port=6379)
p = r.pubsub()

options = webdriver.ChromeOptions()
prefs = {
    "profile.default_content_setting_values.media_stream_mic": 2,
    "profile.default_content_setting_values.media_stream_camera": 2,
    "profile.default_content_setting_values.notifications": 2
}
options.add_argument("start-maximized")
# options.add_argument(
#    "user-data-dir=C:\\Users\\Nathan~1\\Documents\\zoom-python\\UserData")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--mute-audio")
options.add_experimental_option("prefs", prefs)
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)
driver = webdriver.Chrome(options=options)

stealth(driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
        )


def validParticipant(ptc):
    if not ptc.startswith("Everyone") and "<span class=\"chat-receiver-list__appendix\"" not in ptc:
        return True
    else:
        return False


def prepareChat():
    textarea = driver.find_elements_by_class_name("chat-box__chat-textarea")
    if len(textarea) == 0:
        chatbtn = driver.find_element_by_xpath(
            "//button[contains(@aria-label, 'chat')]")
        driver.execute_script("arguments[0].click()", chatbtn)
    textarea = driver.find_elements_by_class_name("chat-box__chat-textarea")
    if len(textarea) == 0:
        raise AssertionError("Textarea is not displayed after clicking")


def validParticipantElement(element):
    return validParticipant(element.get_attribute("innerHTML"))


def saveParticipants(name=script_id):
    participants = list(getDestinationElements())
    f = open("participants-"+name+".txt", "x")
    for participant in participants:
        f.write(participant.get_attribute("innerHTML")+"\n")
    f.close()
    print("File saved to participants-"+name, ", total:", len(participants))


def getDestinationElements():
    dests = driver.find_elements_by_xpath(
        "//li[contains(@class, 'chat-receiver-list__menu-item')]//a")
    return filter(validParticipantElement, dests)


def getDestinations():
    for i in getDestinationElements():
        print(i.get_attribute("innerHTML"))


def generateKey(name):
    cipher = AES.new(key, AES.MODE_EAX)
    nonce = cipher.nonce
    ciphertext, tag = cipher.encrypt_and_digest(str.encode(name))
    return base64.b64encode(nonce).decode("utf-8")+";"+base64.b64encode(ciphertext).decode("utf-8")+";"+base64.b64encode(tag).decode("utf-8")


def decryptCode(ctext):
    try:
        # seperate them by ;
        params = ctext.split(";")
        cipher = AES.new(key, AES.MODE_EAX,
                         nonce=base64.b64decode(str.encode(params[0])))
        plaintext = cipher.decrypt(base64.b64decode(str.encode(params[1])))
        # verify validity
        try:
            cipher.verify(base64.b64decode(str.encode(params[2])))
            print("The message is authentic:", plaintext.decode("utf-8"))
        except ValueError:
            print("Key incorrect or message corrupted")
    except:
        print("Invalid code")


def sendMessage(message):
    textarea = driver.find_element_by_class_name("chat-box__chat-textarea")
    textarea.send_keys(message)
    textarea.send_keys(Keys.ENTER)


def sendMessages():
    prepareChat()
    t1_start = perf_counter()
    dests = getDestinationElements()
    for i in dests:
        # select the chat user
        driver.execute_script("arguments[0].click()", i)
        # send them their name
        sendMessage(generateKey(i.get_attribute("innerHTML")))
        time.sleep(0.1)
    t1_stop = perf_counter()
    print("Done, took", t1_stop-t1_start, "seconds")


def testMessage():
    prepareChat()
    t1_start = perf_counter()
    dests = getDestinationElements()
    for i in dests:
        # select the chat user
        driver.execute_script("arguments[0].click()", i)
        # send them their name
        generateKey(i.get_attribute("innerHTML"))
        sendMessage("This is a test message, this message is for " +
                    i.get_attribute("innerHTML")+", you may ignore this message.")
        time.sleep(0.1)
    t1_stop = perf_counter()
    print("Done, took", t1_stop-t1_start, "seconds")


def join(room):
    driver.get("https://zoom.us/wc/join/"+str(room))


def pub_handler(message):
    cmd = message["data"].decode()
    try:
        eval(cmd)
    except:
        print("error in IPC: ", sys.exc_info()[0])


p.subscribe(**{"zoom": pub_handler})
thread = p.run_in_thread(sleep_time=0.001)


def quit():
    driver.quit()
    thread.stop()
    p.close()
    r.close()
    exit()


def signal_handler(signal, frame):
    print("\nprogram exiting gracefully")
    quit()


signal.signal(signal.SIGINT, signal_handler)
