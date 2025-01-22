
# 打包命令 
``` bash
/Users/librazhang/Library/Python/3.9/bin/pyinstaller --onefile --add-data="templates:templates"  app.py
```

# 建立server命令

``` bash
flask run --host 0.0.0.0 --port=5002 --debug
```

# 部屬server命令

``` bash
sudo /home/lab407/anaconda3/envs/llama_factory/bin/gunicorn -w 4 -b 0.0.0.0:5002 app:app
```