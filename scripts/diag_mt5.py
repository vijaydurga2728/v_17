import MetaTrader5 as mt5

mt5.initialize()
t = mt5.terminal_info()
a = mt5.account_info()
print("terminal_path:", t.path if t else None)
print("data_path:", t.data_path if t else None)
print("account:", a.login if a else None)
print("company:", t.company if t else None)
print("connected:", t.connected if t else None)
mt5.shutdown()
