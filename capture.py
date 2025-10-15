import cv2

# 让用户输入摄像头编号
cam_index = input("请输入摄像头编号（如0、1、2）：")
try:
    cam_index = int(cam_index)
except ValueError:
    print("输入无效，默认使用0号摄像头")
    cam_index = 0

cap = cv2.VideoCapture(cam_index)

# 设置分辨率和帧率（可根据实际需求调整）
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 800)
cap.set(cv2.CAP_PROP_FPS, 30)

while True:
    ret, frame = cap.read()
    if not ret:
        print("无法读取摄像头画面")
        break
    cv2.imshow('U20CAM-9281M', frame)
    # 按q键退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()