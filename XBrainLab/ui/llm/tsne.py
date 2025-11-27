import requests

# res = requests.get("http://127.0.0.1:5000/tsne_log_v2")
# print(res.json())
res = requests.get("http://127.0.0.1:5000/tsne_log_v3_heatmap_class_avg_sim2")
print(res.json())  # 應該會回傳狀態 OK
