#这个需求旨在为server.py在飞书上面创造一个交互的前端
#可以生成一个feishu_master_chen.py的文件，在这个文件里面编写server和飞书交互的服务

服务的具体需求如下
1. 该服务接受来自飞书的信息，然后将收到的信息post到server.py下面的对话/chat下面
2. 等待server.py有回复之后将消息回复到飞书上面
3. server.py在回复消息之后会异步在文件夹里面生成一个voice_id.wav音频文件，需要指定文件夹里是否生成voice_id.wav文件，并且将文件也发送到飞书上面，最多的监听时间为20s（作为参数可以设置），20s之后没有生成文件那就放弃。
4. 所有的消息处理流程因该是一个队列方式，顺序是从1）队列里面取出飞书上面用户输入的消息 2）post到server服务器上面 3）等待server回复的消并发送到飞书上面 4）等待wav音频文件并且发送到飞书上面 5）在队列中取吓一条数据

5. 我希望feishu_master_chen.py启动的时候可以同时启动server.py的服务，关闭的时候可以同时关闭server.py的服务

6. 测试的时候我可以通过飞书app来协助你进行测试

7. feishu_bot.py里面有一个飞书对话回声的demo，你可以参考这个例子来操作飞书

8. 目前我的飞书企业账号开启了im:message，im:message.p2p_msg:readonly,im:message:send_as_bot,因为这个项目涉及到文件传输，你要查一下是不是还要开启其他的权限，需要的话和我说run