import pathlib,threading,webbrowser
from serve_v2 import serve
if __name__=='__main__':
    threading.Timer(1.5,lambda:webbrowser.open('http://127.0.0.1:8017')).start()
    serve(pathlib.Path(__file__).resolve().parents[1],8017)
