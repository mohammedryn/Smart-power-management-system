import pandas as pd
import numpy as np
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

# 1. Load Data
try:
    df = pd.read_csv('../backend/ml_dataset.csv')
except:
    print("Error: ml_dataset.csv not found in backend folder")
    exit()

# 2. Augment Data with FAULT class (Synthetic)
# User said > 0.22A is fault. Level 2 is already ~0.225A (So L2 is technically fault).
# But to be safe, let's add EXTREME faults to ensure robustness.
print("Augmenting data with synthetic FAULT samples...")
np.random.seed(42)
n_faults = 50
fault_data = pd.DataFrame({
    'voltage': np.random.normal(120, 5, n_faults), # 120V Faults
    'current': np.random.normal(0.35, 0.05, n_faults), # > 0.30A
    'power': np.random.normal(40, 5, n_faults),
    'label': ['FAULT'] * n_faults
})

# Add some "LEVEL_2" as "WARNING" if user wants? 
# For now, let's keep user labels (LEVEL_1, LEVEL_2, IDLE) + FAULT.
df = pd.concat([df, fault_data], ignore_index=True)

print("Dataset Class Distribution:")
print(df['label'].value_counts())

# 3. Preprocessing
X = df[['voltage', 'current', 'power']].values
y_str = df['label'].values

encoder = LabelEncoder()
y = encoder.fit_transform(y_str)
classes = encoder.classes_
print(f"Classes: {classes}")

# Save class map for Firmware
with open('../firmware/src/class_map.h', 'w') as f:
    f.write("// Auto-generated class map\n")
    joined_classes = '", "'.join(classes)
    f.write(f'const char* CLASS_NAMES[] = {{ "{joined_classes}" }};\n')

# Split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 4. Define Model
model = tf.keras.Sequential([
    tf.keras.layers.Dense(16, activation='relu', input_shape=(3,)),
    tf.keras.layers.Dense(8, activation='relu'),
    tf.keras.layers.Dense(len(classes), activation='softmax')
])

model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])

# 5. Train
print("Training...")
model.fit(X_train, y_train, epochs=200, batch_size=8, verbose=0)
loss, acc = model.evaluate(X_test, y_test, verbose=0)
print(f"Test Accuracy: {acc*100:.2f}%")

# 6. Convert to TFLite
converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT] # Quantize for size
tflite_model = converter.convert()

# Save binary
with open('model.tflite', 'wb') as f:
    f.write(tflite_model)

# 7. Convert to C Source (xxd style)
def convert_to_c_array(bytes_data):
    hex_str = ", ".join([f"0x{b:02x}" for b in bytes_data])
    return f"const unsigned char model_data[] = {{ {hex_str} }};\nconst int model_data_len = {len(bytes_data)};"

with open('../firmware/src/model_data.h', 'w') as f:
    f.write("#ifndef MODEL_DATA_H\n#define MODEL_DATA_H\n\n")
    f.write(convert_to_c_array(tflite_model))
    f.write("\n\n#endif")

print("Success! Model saved to firmware/src/model_data.h")
print(f"Top detected class for 0.35A: {classes[np.argmax(model.predict([[120, 0.35, 40]]))]}" )
