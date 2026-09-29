print("hello world")
data = [166,-27,138,-54,110,-83,83,-110,55,-138,27,-166,0]
data2 = [26,-168,-2,164,-29]
data = data2
ans = []
for i in range(len(data)):
    if i == 1:
        continue
    if data[i] < data[i-1]:
        ans.append(data[i] + 360 - data[i-1])
    else: ans.append(data[i] - data[i-1])
print(ans)
