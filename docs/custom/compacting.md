\################当前compact\_node的问题###################

目前消息compact\_node的位置：

llm\_node->compact\_node->end

目前compact\_node的逻辑：

如果messages里面的token数量小于阈值，那么就messages就不变，如果大于阈值，那么messages保留system message还有最后一条ai消息

目前compact\_node的问题：

1. 会删除原有messages，导致进一步的数据处理困难
2. 删除messages可能会导致messages里面的顺序发生变化，可能最后一条数据不是ai生成的回答数据



\################改进之后compact\_node###################

改进之后compact\_node的位置：

entry\_point(或者tool node)->compact\_node->llm node、

改进之后compact\_node的逻辑

1. 在AgentState中定义一个新的字段叫做compact\_messages
2. 在compact\_node中先是判断一下messages的增量，定义为new\_messages
3. 如果compact\_messages+new\_messages的总token数量小于某个阈值，那么更新compact\_messages=compact\_messages+new\_messages
4. 如果compact\_messages+new\_messages的总token数量大于等于某个阈值，那么更新compact\_messages=summarize\_messages(compact\_messages+new\_messages)



在call\_model里面也要做相应的修改：

原来call\_model中的大模型的输入是system\_prompt(包括算命师人设和工具信息)+messages，现在变成system\_prompt+compact\_messages



\################修改compact\_node之后的测试###################

1\.首先单独测试一下compact\_node,分两种情况一种是compact\_messages+new\_messages不超过阈值，第二种是超过阈值，看一看输出的结果是否符合预期

2\. 改动call\_model之后整个agent是否能够正常输出，使用test\_agent.py脚本因该就可以了

3\. server.py我自己可以测试



