�����÷���
��ѹ������Ŀ¼, ִ�������transcode����
./transcode -i /home/input_dir -o /home/output_dir --config-file ./transcode.json

transcode���������������
-l: Ĭ�ϳ���Ὣ֮��־д��./transcode.log�ļ��У������������ָ������ļ���
--max-tasks: ���Ʋ��е���������
--no-skip: ����Ĭ��ת��ǰ�������Ŀ¼�Ƿ��ж�Ӧ�ļ�������в���ʱ��������ƥ�䣬��������Ӧ��ת�롣--no-skip�ɽ�ֹ����Ϊ��


��������Ŀ��ƣ�
�������ͨ�������ļ����ƣ�Ĭ�϶�ȡ./transcode.json�ļ���Ҳ������transcode�������������--config-file����ָ����������ļ�����
��д�Ͳ���˵����ο�ѹ�����Դ���transcode.json��
��Ҫ���ֱַ��ʲ��䣬ȥ��width, height, aspect��������ɡ�

ע�⣺
    �����ļ�Ϊjson��ʽ����ȡ���ݴ��Խϲ��С�ı�д��
    �����׳�����ĵط�����©��ĩβ�Ķ��Ż�����˲���Ҫ�Ķ��š�
    ÿ����治Ҫ©�����š�
    ]��}ǰ������н���û�ж��š�
    ������һ���ڲ�Ҫͬʱ��ע�ͺʹ��롣���дע�����õ������У�������˫б�ܿ�ͷ��


ɾ��mcs����:
���ԭ��װ��mcs�İ汾��δ�����ͻ����ɾ����
find /etc/ -iname "*mcs*"|xargs rm -rf
killall -9 mcs.elf ffmpeg sample_encode startup.sh 


���ʹ��ssh��¼����������ִ��ת�����ssh�����쳣�ն˻ᵼ��ת��������ֹ����ʹ��screen���߱�������⡣screen�Ľ������Ϻܶ࣬���� �Ǽ򵥵��÷���

ssh��¼��������
screen -S yoursessionname
�˳���CTRL-a d

�˳����쳣�Ͽ����������
screen -ls
    9969.yoursessionname    (07/30/2014 09:09:31 AM)    (Detached)
screen -r yoursessionname 
