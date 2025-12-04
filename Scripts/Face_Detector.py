"""
Face_Detector.py

Herramienta de depuración para inspección y calibración del Face Mesh (MediaPipe).

Resumen:
    Versión simplificada del sistema de seguimiento ocular destinada a pruebas
    y visualización rápida de landmarks faciales. Permite comprobar detección
    en la cámara, visualizar todos los puntos de la malla, y generar una vista
    virtual simplificada de los ojos para calibración.

Funcionalidad principal:
    - Captura vídeo desde la cámara por defecto.
    - Dibuja Face Mesh y landmarks en el frame principal.
    - Muestra una ventana "ESCANEO FACIAL" con todos los landmarks marcados.
    - Calcula centros de ojos y muestra una emulación virtual simple.

Autor: Alejandro Aguirre Diaz
"""

import cv2
import numpy as np
import mediapipe as mp
import time

class SimpleEyeTracker:
    def __init__(self):
        """Versión simplificada del tracker para debugging"""
        # MediaPipe Face Mesh
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=False,  # Simplificado
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # Para dibujar
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Landmarks básicos de ojos
        self.LEFT_EYE = [362, 385, 387, 263, 373, 380]
        self.RIGHT_EYE = [33, 160, 158, 133, 153, 144]
    
    def run(self):
        """Ejecutar versión simple"""
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print("Error: No se pudo acceder a la cámara")
            return
        
        print("Sistema simple iniciado - Presiona 'q' para salir")
        print("Ventanas: Principal, Virtual y Escaneo Facial")
        
        # Ventana virtual simple
        virtual_frame = np.zeros((300, 500, 3), dtype=np.uint8)
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Voltear para espejo
            frame = cv2.flip(frame, 1)
            
            # Convertir a RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb_frame)
            
            # Limpiar ventana virtual
            virtual_frame.fill(0)
            
            # Crear frame separado para escaneo facial (solo landmarks)
            face_scan_frame = np.ones_like(frame) * 255  # Fondo blanco del mismo tamaño
            
            if results.multi_face_landmarks:
                face_landmarks = results.multi_face_landmarks[0]
                
                # Dibujar mesh facial en frame principal
                self.mp_drawing.draw_landmarks(
                    frame, face_landmarks, self.mp_face_mesh.FACEMESH_CONTOURS)
                
                # Dibujar SOLO los landmarks en la ventana de escaneo facial
                # Usar puntos rojos como se solicita
                landmarks = face_landmarks.landmark
                h, w = frame.shape[:2]
                
                # Dibujar todos los landmarks como puntos rojos en movimiento
                for landmark in landmarks:
                    x = int(landmark.x * w)
                    y = int(landmark.y * h)
                    # Puntos rojos brillantes para el escaneo
                    cv2.circle(face_scan_frame, (x, y), 2, (0, 0, 255), -1)
                
                # Añadir puntos más grandes para ojos y boca para mejor visualización
                # Ojos
                for i in self.LEFT_EYE + self.RIGHT_EYE:
                    x = int(landmarks[i].x * w)
                    y = int(landmarks[i].y * h)
                    cv2.circle(face_scan_frame, (x, y), 4, (0, 100, 255), -1)  # Rojo-naranja para ojos
                
                # Contorno de cara
                face_contour = [10, 151, 9, 8, 168, 6, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
                for i in face_contour:
                    if i < len(landmarks):
                        x = int(landmarks[i].x * w)
                        y = int(landmarks[i].y * h)
                        cv2.circle(face_scan_frame, (x, y), 3, (0, 50, 255), -1)  # Rojo más oscuro para contorno
                
                # Obtener landmarks para cálculos
                landmarks = face_landmarks.landmark
                h, w = frame.shape[:2]
                
                # Calcular centros de ojos
                left_eye_points = [(int(landmarks[i].x * w), int(landmarks[i].y * h)) 
                                  for i in self.LEFT_EYE]
                right_eye_points = [(int(landmarks[i].x * w), int(landmarks[i].y * h)) 
                                   for i in self.RIGHT_EYE]
                
                # Centros
                left_center = (sum(p[0] for p in left_eye_points) // len(left_eye_points),
                              sum(p[1] for p in left_eye_points) // len(left_eye_points))
                right_center = (sum(p[0] for p in right_eye_points) // len(right_eye_points),
                               sum(p[1] for p in right_eye_points) // len(right_eye_points))
                
                # Marcar centros en frame principal
                cv2.circle(frame, left_center, 5, (0, 255, 0), -1)
                cv2.circle(frame, right_center, 5, (0, 255, 0), -1)
                
                # Marcar centros en ventana de escaneo con círculos más grandes
                cv2.circle(face_scan_frame, left_center, 8, (0, 255, 255), 2)  # Amarillo para centros
                cv2.circle(face_scan_frame, right_center, 8, (0, 255, 255), 2)
                
                # Información en ventana de escaneo
                cv2.putText(face_scan_frame, "ESCANEO FACIAL EN TIEMPO REAL", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                cv2.putText(face_scan_frame, f"Landmarks: {len(landmarks)}", (10, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                cv2.putText(face_scan_frame, "Puntos rojos: Face Mesh", (10, 85), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 100), 1)
                
                # Emulación simple en ventana virtual
                # Calcular posición normalizada
                avg_x = (left_center[0] + right_center[0]) / (2 * w)
                avg_y = (left_center[1] + right_center[1]) / (2 * h)
                
                # Posiciones virtuales
                virt_left_x = int(125 + (avg_x - 0.5) * 100)
                virt_left_y = int(150 + (avg_y - 0.5) * 50)
                virt_right_x = int(375 + (avg_x - 0.5) * 100)
                virt_right_y = int(150 + (avg_y - 0.5) * 50)
                
                # Dibujar ojos virtuales
                cv2.circle(virtual_frame, (virt_left_x, virt_left_y), 30, (255, 255, 255), 2)
                cv2.circle(virtual_frame, (virt_right_x, virt_right_y), 30, (255, 255, 255), 2)
                cv2.circle(virtual_frame, (virt_left_x, virt_left_y), 10, (0, 255, 0), -1)
                cv2.circle(virtual_frame, (virt_right_x, virt_right_y), 10, (0, 255, 0), -1)
                
                # Info
                cv2.putText(virtual_frame, f"Pos X: {avg_x:.2f}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(virtual_frame, f"Pos Y: {avg_y:.2f}", (10, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # Info en frame principal
                cv2.putText(frame, f"Rostro detectado", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                # No hay detección
                cv2.putText(frame, "No se detecta rostro", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                cv2.putText(virtual_frame, "SIN DETECCION", (150, 150), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                
                # Ventana de escaneo sin detección
                face_scan_frame = np.ones_like(frame) * 255  # Fondo blanco
                cv2.putText(face_scan_frame, "SIN DETECCION FACIAL", (100, 200), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                cv2.putText(face_scan_frame, "Posiciona tu rostro frente a la camara", (50, 250), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
            
            # Mostrar ventanas
            cv2.imshow('Simple Eye Tracker - Principal', frame)
            cv2.imshow('Simple Eye Tracker - Virtual', virtual_frame)
            cv2.imshow('ESCANEO FACIAL - Landmarks en Tiempo Real', face_scan_frame)  # Nueva ventana
            
            # Salir
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()
        print("Sistema simple terminado")

if __name__ == "__main__":
    tracker = SimpleEyeTracker()
    tracker.run()