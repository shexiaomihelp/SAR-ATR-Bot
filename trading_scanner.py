# 可優化的代碼示例
# 可優化點1: 使用傳統for循環
squares = []
for i in range(10):
    squares.append(i*i)

# 可優化點2: 使用字符串拼接
name = "John"
age = 25
message = "My name is " + name + " and I am " + str(age) + " years old."

# 可優化點3: 使用range(len())獲取索引
fruits = ["apple", "banana", "cherry"]
for i in range(len(fruits)):
    print(i, fruits[i])

# 可優化點4: 使用傳統文件操作
file = open("data.txt", "r")
content = file.read()
file.close()

# 可優化點5: 使用全局變量
global_var = 0

def increment():
    global global_var
    global_var += 1
