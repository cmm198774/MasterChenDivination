\#帮我实现一下RAG数据库的数据添加（实现server.py里面 def add\_urls()）

1. 读取指定的url网页里面的数据，并且添加到rag数据库里面，
2. 分词器可以使用RecursiveCharacterTextSplitter，chunk\_size默认是1000，overlap是100
3. embedding使用text-embedding-v3，默认把数据存入local\_qdrand里面，collection就用yunshi\_2026



\#测试的话

1\.先实现非fast api版本,测试的url连接为G:\\JupyterProject\\20260626\_Agent实战\\html\\八字未来运势\_免费八字未来预测\_四柱八字流年运势\_未来趋势解析-缘份居.html

2\.加载了测试url之后运行一下get\_info\_from\_local\_db看看是否可以从数据库中正确把数据读出来

3\.然后再把非fast\_api的版本填充到server.py里面 def add\_urls()中，post的测试我自己来做



