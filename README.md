# xiaotie
想做个麦麦



消息类：

```
Class MsgBase

class FriendMsg(Msgbase)

class Response(Msgbase)
从缓冲池得到Response，将需要回复的消息以类为单位存储

```



接收消息->加入缓冲池->缓冲池检查是否回复->若有T，则触发回复，调用回复函数

回复函数内容：1. 关键词拆分并添加到db	2. 调用LLM与prompt	3. 情绪模块改变prompt	4. 输送给输出函数





