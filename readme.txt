基本用法：
解压到任意目录, 执行里面的transcode程序
./transcode -i /home/input_dir -o /home/output_dir --config-file ./transcode.json

transcode程序的其他参数：
-l: 默认程序会将之日志写到./transcode.log文件中，可用这个参数指定别的文件。
--max-tasks: 控制并行的任务数。
--no-skip: 程序默认转码前会检查输出目录是否有对应文件，如果有并且时长和输入匹配，会跳过对应的转码。--no-skip可禁止此行为。


编码参数的控制：
编码参数通过配置文件控制，默认读取./transcode.json文件，也可在在transcode程序的命令行用--config-file参数指定你的配置文件名。
编写和参数说明请参考压缩包自带的transcode.json。
如要保持分辨率不变，去掉width, height, aspect的配置项即可。

注意：
    配置文件为json格式，读取的容错性较差，请小心编写。
    最容易出问题的地方就是漏掉末尾的逗号活添加了不必要的逗号。
    每项后面不要漏掉逗号。
    ]和}前面的那行结束没有逗号。
    另外在一行内不要同时有注释和代码。如果写注释请用单独的行，并用左双斜杠开头。


删除mcs服务:
如果原来装有mcs的版本，未避免冲突建议删除。
find /etc/ -iname "*mcs*"|xargs rm -rf
killall -9 mcs.elf ffmpeg sample_encode startup.sh 


如果使用ssh登录到服务器上执行转码程序，ssh连接异常终端会导致转码程序的终止。可使用screen工具避免此问题。screen的讲解网上很多，下面 是简单的用法：

ssh登录到服务器
screen -S yoursessionname
退出：CTRL-a d

退出或异常断开后的重连：
screen -ls
    9969.yoursessionname    (07/30/2014 09:09:31 AM)    (Detached)
screen -r yoursessionname 
