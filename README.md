# xiaotie
想做个麦麦



消息类：

```
Class MsgBase
class FriendMsg(Msgbase)
class Response(Msgbase)

```
## 总结构
app.py运行,启动线程:  
net_manager.memory_process记忆网络更新  
moodupdater.update_in_timeloop随时间流逝心情的递减等变化更新  
启动flask后端,监听前端消息  

api.py初始化msg_process,将其加入缓冲池作为消息处理函数  message_buffer.set_handler(msg_process)  
  
监听部分:  
获得消息,转化为消息类,存入数据库与缓冲池  
缓冲池自动出列消息,合并消息送入api.msg_process




接收消息->加入缓冲池->缓冲池检查是否回复->若有T，则触发回复，调用回复函数

回复函数内容：
1. 关键词拆分并添加到db	
2. 调用LLM与prompt	
3. 情绪模块调整prompt
4. 输送给输出函数,进行回复


欲完成的agent结构:  
数据接收与初步处理:前端,缓冲池,  
深度思索:调用LLM生成任务列表,调用工具,调用结束后评估结果,决定回复或再次生成任务列表  
输出函数:  





情绪模块: mood与emotion

分为三类值

基础情绪: 喜悦 ↔ 悲伤 愤怒 ↔ 恐惧 惊讶 ↔ 期待 厌恶 ↔ 信任

复杂情绪: 

```
('喜悦', '信任' ): '爱',
('信任', '恐惧' ): '顺从',
('恐惧', '惊讶' ): '惊恐',
('惊讶', '悲伤' ): '失望',
('悲伤', '厌恶' ): '悔恨',
('厌恶', '愤怒' ): '蔑视',
('愤怒', '期待' ): '攻击性',
('期待', '喜悦' ): '乐观',
```

```
emotion_manager:
分析文本,给出基础与复杂情感的强度,并尝试输出对应描述
基础情感给出对应评级,存放在self.response_content
复杂情感根据基础情感计算得出

mood_manager:
分为两个主要函数,timeloop与msgloop
timeloop由定时线程触发
msgloop塞在消息缓存池里

timeloop:用于衰减兴趣与心情,根据空闲时间来选择不同衰减速率
msgloop:与外界相连,获得消息,



```





