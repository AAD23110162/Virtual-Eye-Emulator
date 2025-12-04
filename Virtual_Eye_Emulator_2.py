
# Emulador de vista virtual en tiempo real
# Autor: Alejandro Aguirre Diaz
import cv2
import numpy as np
import mediapipe as mp
import time
import math
import os
from scipy.spatial import distance as dist

class EyeTracker:
    def __init__(self):
        """
        Inicializa el sistema de seguimiento ocular
        """
        # Configurar MediaPipe Face Mesh
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # Configurar MediaPipe para dibujar
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        
        # Índices de landmarks para los ojos (MediaPipe Face Mesh)
        self.LEFT_EYE_LANDMARKS = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
        self.RIGHT_EYE_LANDMARKS = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
        
        # Landmarks para detección de parpadeo
        self.LEFT_EYE_CONTOUR = [33, 160, 158, 133, 153, 144]
        self.RIGHT_EYE_CONTOUR = [362, 385, 387, 263, 373, 380]
        
        # Landmarks específicos para iris (detección mejorada de mirada)
        self.LEFT_IRIS = [468, 469, 470, 471, 472]
        self.RIGHT_IRIS = [473, 474, 475, 476, 477]
        
        # Landmarks para detección de cejas
        self.LEFT_EYEBROW = [70, 63, 105, 66, 107, 55, 65, 52, 53, 46]
        self.RIGHT_EYEBROW = [296, 334, 293, 300, 276, 283, 282, 295, 285, 336]
        
        # Variables para tracking
        self.blink_threshold = 0.20  # Umbral más bajo para detectar parpadeos más fácilmente
        self.wink_threshold = 0.18   # Umbral para detectar guiños (más bajo que parpadeo)
        self.consecutive_frames = 2   # Menos frames consecutivos para detección más rápida
        self.left_blink_counter = 0
        self.right_blink_counter = 0
        self.left_blink_total = 0
        self.right_blink_total = 0
        
        # Variables para detección de guiños y estados de ojos
        self.left_wink_counter = 0
        self.right_wink_counter = 0
        self.both_eyes_closed = False
        self.left_winking = False
        self.right_winking = False
        
        # Variables para el emulador virtual (espacio 128x64 escalado al doble = 256x128)
        self.virtual_window_size = (600, 300)
        self.left_eye_pos = (225, 150)   # Separación de 150px
        self.right_eye_pos = (375, 150)  # Separación de 150px entre centros
        
        # Historial de movimientos para suavizado (reducido para mayor responsividad)
        self.eye_movement_history = []
        self.history_size = 3  # Menos frames para respuesta más rápida
        
        # Modo de visualización
        self.visualization_mode = "RECTANGULOS"  # "RECTANGULOS", "REDONDEADOS" o "AM"
        
        # === SISTEMA DE GRABACIÓN DE ANIMACIONES ===
        self.is_recording = False
        self.animation_frames = []
        self.recording_start_time = None
        self.max_recording_time = 60.0  # Máximo 60 segundos de grabación
        self.frame_interval = 1.0 / 30.0  # 30 FPS para grabación
        self.last_frame_time = 0.0
        
        # Variables para grabación de video
        self.video_writer = None
        self.video_frames = []
        self.recording_filename = None
        
        # Crear carpetas si no existen
        self.json_folder = "Animaciones JSON"
        self.video_folder = "AnimacionMP4"
        os.makedirs(self.json_folder, exist_ok=True)
        os.makedirs(self.video_folder, exist_ok=True)
        
        # === ESTADO PARA ANIMACIÓN AM (similar a ESP32) ===
        self.am_openness = 0.0      # 0-100, se abre/cierra
        self.am_open_dir = 1        # +1 abriendo, -1 cerrando
        self.am_last_update = time.time()
        self.AM_FRAME_INTERVAL = 0.04  # ~25 FPS
        self.am_phase = 0.0

    def calculate_eye_aspect_ratio(self, eye_landmarks, frame_shape):
        """
        Calcula la relación de aspecto del ojo (EAR) para detectar parpadeos
        """
        # Convertir landmarks normalizados a coordenadas de pixel
        points = []
        for landmark in eye_landmarks:
            x = int(landmark.x * frame_shape[1])
            y = int(landmark.y * frame_shape[0])
            points.append((x, y))
        
        # Calcular distancias verticales
        A = dist.euclidean(points[1], points[5])
        B = dist.euclidean(points[2], points[4])
        
        # Calcular distancia horizontal
        C = dist.euclidean(points[0], points[3])
        
        # Calcular EAR
        ear = (A + B) / (2.0 * C)
        return ear

    def get_eye_center(self, eye_landmarks, frame_shape):
        """
        Calcula el centro del ojo basado en los landmarks
        """
        points = []
        for landmark in eye_landmarks:
            x = int(landmark.x * frame_shape[1])
            y = int(landmark.y * frame_shape[0])
            points.append((x, y))
        
        # Calcular centroide
        x_coords = [p[0] for p in points]
        y_coords = [p[1] for p in points]
        center_x = sum(x_coords) // len(x_coords)
        center_y = sum(y_coords) // len(y_coords)
        
        return (center_x, center_y)

    def get_iris_center(self, landmarks, is_left_eye, frame_shape):
        """
        Calcula el centro del iris para detección más precisa de mirada
        """
        try:
            if is_left_eye:
                iris_landmarks = self.LEFT_IRIS
            else:
                iris_landmarks = self.RIGHT_IRIS
            
            # Obtener coordenadas del iris
            iris_points = []
            for landmark_id in iris_landmarks:
                if landmark_id < len(landmarks):
                    landmark = landmarks[landmark_id]
                    x = int(landmark.x * frame_shape[1])
                    y = int(landmark.y * frame_shape[0])
                    iris_points.append((x, y))
            
            if len(iris_points) >= 3:  # Necesitamos al menos 3 puntos
                # Calcular centroide del iris
                x_coords = [p[0] for p in iris_points]
                y_coords = [p[1] for p in iris_points]
                center_x = sum(x_coords) // len(x_coords)
                center_y = sum(y_coords) // len(y_coords)
                return (center_x, center_y)
            
        except:
            pass
        
        return None

    def get_eyebrow_height(self, eyebrow_landmarks, eye_landmarks, frame_shape):
        """
        Calcula la altura relativa de las cejas respecto a los ojos
        """
        # Obtener coordenadas de cejas
        eyebrow_points = []
        for landmark in eyebrow_landmarks:
            x = int(landmark.x * frame_shape[1])
            y = int(landmark.y * frame_shape[0])
            eyebrow_points.append((x, y))
        
        # Obtener coordenadas de ojos
        eye_points = []
        for landmark in eye_landmarks:
            x = int(landmark.x * frame_shape[1])
            y = int(landmark.y * frame_shape[0])
            eye_points.append((x, y))
        
        # Calcular altura promedio de cejas y ojos
        eyebrow_y = sum(p[1] for p in eyebrow_points) / len(eyebrow_points)
        eye_y = sum(p[1] for p in eye_points) / len(eye_points)
        
        # Distancia entre ceja y ojo (normalizada)
        distance = abs(eyebrow_y - eye_y)
        
        # Normalizar la distancia (valores típicos entre 20-60 pixeles)
        normalized_distance = max(0.0, min(1.0, (distance - 20) / 40))
        
        return normalized_distance

    def detect_eye_state(self, left_ear, right_ear):
        """
        Detecta el estado de los ojos: guiño izquierdo, guiño derecho, ambos cerrados, o normales
        """
        left_closed = left_ear < self.wink_threshold
        right_closed = right_ear < self.wink_threshold
        
        # Detectar ambos ojos cerrados
        if left_closed and right_closed:
            self.both_eyes_closed = True
            self.left_winking = False
            self.right_winking = False
            return "AMBOS_CERRADOS"
        
        # Detectar guiño izquierdo (ojo izquierdo cerrado, derecho abierto)
        elif left_closed and not right_closed:
            self.left_wink_counter += 1
            if self.left_wink_counter >= self.consecutive_frames:
                self.left_winking = True
                self.right_winking = False
                self.both_eyes_closed = False
                return "GUINANDO_IZQUIERDO"
        else:
            self.left_wink_counter = 0
            
        # Detectar guiño derecho (ojo derecho cerrado, izquierdo abierto)
        if right_closed and not left_closed:
            self.right_wink_counter += 1
            if self.right_wink_counter >= self.consecutive_frames:
                self.right_winking = True
                self.left_winking = False
                self.both_eyes_closed = False
                return "GUINANDO_DERECHO"
        else:
            self.right_wink_counter = 0
            
        # Ambos ojos abiertos
        if not left_closed and not right_closed:
            self.left_winking = False
            self.right_winking = False
            self.both_eyes_closed = False
            return "AMBOS_ABIERTOS"
        
        return "NORMAL"

    def detect_eye_movement(self, left_center, right_center, frame_shape, landmarks=None):
        """
        Detecta la dirección del movimiento de los ojos con detección mejorada usando iris
        """
        # Si tenemos landmarks, usar detección mejorada con iris
        if landmarks is not None:
            try:
                # Obtener centros de iris para mayor precisión
                left_iris_center = self.get_iris_center(landmarks, True, frame_shape)
                right_iris_center = self.get_iris_center(landmarks, False, frame_shape)
                
                # Usar centros de iris si están disponibles
                if left_iris_center and right_iris_center:
                    left_center = left_iris_center
                    right_center = right_iris_center
            except:
                # Fallback a detección estándar si hay problemas con iris
                pass
        
        # Normalizar posiciones (0-1)
        left_x_norm = left_center[0] / frame_shape[1]
        left_y_norm = left_center[1] / frame_shape[0]
        right_x_norm = right_center[0] / frame_shape[1]
        right_y_norm = right_center[1] / frame_shape[0]
        
        # Promediar ambos ojos para obtener dirección general de la mirada
        gaze_x = (left_x_norm + right_x_norm) / 2
        gaze_y = (left_y_norm + right_y_norm) / 2
        
        # Añadir al historial para suavizado
        self.eye_movement_history.append((gaze_x, gaze_y))
        if len(self.eye_movement_history) > self.history_size:
            self.eye_movement_history.pop(0)
        
        # Calcular promedio suavizado
        avg_x = sum(pos[0] for pos in self.eye_movement_history) / len(self.eye_movement_history)
        avg_y = sum(pos[1] for pos in self.eye_movement_history) / len(self.eye_movement_history)
        
        # Determinar dirección con umbrales más sensibles
        direction = "CENTRO"
        if avg_x < 0.42:  # Más sensible para izquierda
            direction = "IZQUIERDA"
        elif avg_x > 0.58:  # Más sensible para derecha
            direction = "DERECHA"
        
        if avg_y < 0.42:  # Más sensible para arriba
            direction += "_ARRIBA"
        elif avg_y > 0.58:  # Más sensible para abajo
            direction += "_ABAJO"
        
        return direction, (avg_x, avg_y)

    def draw_am_wave(self, frame, center_x, center_y, left_openness, right_openness, phase_offset, width, color):
        """
        Dibuja una onda AM tipo ojo ESP32 con apertura independiente por mitad:
        - left_openness: 0-100 (apertura del ojo izquierdo para la mitad izquierda)
        - right_openness: 0-100 (apertura del ojo derecho para la mitad derecha) 
        - phase_offset: fase para 'mirar' izq/der
        """
        base_amp = 4.0  # Amplitud base aumentada al doble (de 2.0 a 4.0)
        # Rango de amplitud extra aumentado al doble de 0-25 a 0-50
        left_extra_amp = np.interp(left_openness, [0, 100], [0, 50])
        right_extra_amp = np.interp(right_openness, [0, 100], [0, 50])
        carrier_k = 0.5  # frecuencia de portadora reducida a la mitad (de 1.2 a 0.6)

        prev_x = center_x - width // 2
        prev_y = center_y
        half_width = width // 2

        for i in range(width):
            x = center_x - width // 2 + i
            t = i / (width - 1)

            # Determinar qué mitad estamos dibujando
            if i < half_width:
                # Mitad izquierda: usar apertura del ojo izquierdo
                extra_amp = left_extra_amp
            else:
                # Mitad derecha: usar apertura del ojo derecho  
                extra_amp = right_extra_amp

            # envolvente tipo coseno (como en el ESP32)
            env = base_amp + extra_amp * (0.5 * (1.0 + math.cos(4.0 * math.pi * t + math.pi)))

            y = center_y + int(env * math.sin(carrier_k * i + phase_offset))

            cv2.line(frame, (prev_x, prev_y), (x, y), color, 2)
            prev_x, prev_y = x, y

        # línea base (opcional)
        cv2.line(frame, (center_x - width // 2, center_y),
                 (center_x + width // 2, center_y), (80, 80, 80), 1)

    def start_recording(self):
        """
        Inicia la grabación de animaciones (JSON + MP4)
        """
        if not self.is_recording:
            self.is_recording = True
            self.animation_frames = []
            self.video_frames = []
            self.recording_start_time = time.time()
            self.last_frame_time = time.time()
            
            # Generar nombre base con timestamp
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            self.recording_filename = f"animation_{timestamp}"
            
            print("[GRABACIÓN] Iniciada - Presiona 'P' para detener")
            print(f"[GRABACIÓN] Archivos: {self.recording_filename}.json y {self.recording_filename}.mp4")
        else:
            print("[GRABACIÓN] Ya está en progreso...")
    
    def stop_recording(self):
        """
        Detiene la grabación y guarda los archivos JSON y MP4
        """
        if self.is_recording:
            self.is_recording = False
            total_time = time.time() - self.recording_start_time
            
            if len(self.animation_frames) > 0 and len(self.video_frames) > 0:
                # === GUARDAR ARCHIVO JSON ===
                json_filename = os.path.join(self.json_folder, f"{self.recording_filename}.json")
                
                # Preparar datos para guardar
                animation_data = {
                    "duration": total_time,
                    "total_frames": len(self.animation_frames),
                    "fps": len(self.animation_frames) / total_time if total_time > 0 else 30,
                    "resolution": {
                        "width": 128,
                        "height": 64
                    },
                    "frames": self.animation_frames
                }
                
                # Guardar archivo JSON
                try:
                    import json
                    with open(json_filename, 'w') as f:
                        json.dump(animation_data, f, indent=2)
                    print(f"[GRABACIÓN] JSON guardado: {json_filename}")
                except Exception as e:
                    print(f"[GRABACIÓN] Error al guardar JSON: {str(e)}")
                
                # === GUARDAR ARCHIVO MP4 ===
                mp4_filename = os.path.join(self.video_folder, f"{self.recording_filename}.mp4")
                
                try:
                    # Configuración del codec
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    fps = 30.0  # FPS del video
                    frame_size = (800, 400)  # Tamaño del frame virtual
                    
                    # Crear VideoWriter
                    video_writer = cv2.VideoWriter(mp4_filename, fourcc, fps, frame_size)
                    
                    # Escribir todos los frames capturados
                    for frame in self.video_frames:
                        video_writer.write(frame)
                    
                    # Cerrar el writer
                    video_writer.release()
                    
                    print(f"[GRABACIÓN] MP4 guardado: {mp4_filename}")
                    print(f"[GRABACIÓN] Video: {len(self.video_frames)} frames, {total_time:.2f}s")
                    
                except Exception as e:
                    print(f"[GRABACIÓN] Error al guardar MP4: {str(e)}")
                
                print(f"[GRABACIÓN] Completada - JSON: {len(self.animation_frames)} frames, MP4: {len(self.video_frames)} frames")
                
            else:
                print("[GRABACIÓN] No hay frames para guardar")
                
            # Limpiar variables
            self.video_frames = []
            self.recording_filename = None
        else:
            print("[GRABACIÓN] No hay grabación activa")
    
    def capture_frame_for_recording(self, left_ear, right_ear, gaze_direction, gaze_pos, left_brow_height, right_brow_height, virtual_frame):
        """
        Captura un frame actual para la grabación (JSON + MP4)
        """
        if not self.is_recording:
            return
        
        current_time = time.time()
        
        # Verificar límite de tiempo
        if current_time - self.recording_start_time > self.max_recording_time:
            print("[GRABACIÓN] Límite de tiempo alcanzado (60s)")
            self.stop_recording()
            return
        
        # Controlar frecuencia de captura (30 FPS)
        if current_time - self.last_frame_time >= self.frame_interval:
            # === CAPTURAR DATOS JSON ===
            frame_data = {
                "timestamp": current_time - self.recording_start_time,
                "mode": self.visualization_mode,
                "left_ear": round(left_ear, 3),
                "right_ear": round(right_ear, 3),
                "gaze_x": round(gaze_pos[0], 3),
                "gaze_y": round(gaze_pos[1], 3),
                "left_brow": round(left_brow_height, 2),
                "right_brow": round(right_brow_height, 2),
                "direction": gaze_direction
            }
            
            # Solo para modo AM, agregar datos específicos
            if self.visualization_mode == "AM":
                frame_data["am_phase"] = round(self.am_phase, 2)
            
            self.animation_frames.append(frame_data)
            
            # === CAPTURAR FRAME DE VIDEO ===
            # Usar una copia exacta del frame que se está mostrando en pantalla
            # para mantener proporcionalidad y evitar distorsión
            video_frame_exact = virtual_frame.copy()
            
            # Agregar información de grabación al frame (sin afectar la visualización original)
            elapsed = current_time - self.recording_start_time
            cv2.putText(video_frame_exact, f"REC {elapsed:.1f}s", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            cv2.circle(video_frame_exact, (760, 30), 10, (0, 0, 255), -1)  # Círculo rojo de grabación
            
            # Agregar frame al buffer de video
            self.video_frames.append(video_frame_exact)
            
            self.last_frame_time = current_time
            
            # Mostrar progreso cada 30 frames
            if len(self.animation_frames) % 30 == 0:
                print(f"[GRABACIÓN] {elapsed:.1f}s - JSON: {len(self.animation_frames)} frames, MP4: {len(self.video_frames)} frames")

    def update_am_state(self, client_detected, gaze_direction):
        """
        Actualiza la 'apertura' y la fase de la onda AM igual que en el ESP32.
        client_detected: True si tenemos cara detectada (equivalente a BLE conectado)
        gaze_direction: texto tipo 'IZQUIERDA', 'DERECHA', 'CENTRO'
        """
        now = time.time()
        if now - self.am_last_update < self.AM_FRAME_INTERVAL:
            return
        self.am_last_update = now

        # Si no hay rostro → "durmiendo": apertura 0
        if not client_detected:
            self.am_openness = 0
            return

        # Abrir/cerrar tipo respiración
        self.am_openness += self.am_open_dir * 2
        self.am_openness = max(0, min(100, self.am_openness))

        if self.am_openness in (0, 100):
            self.am_open_dir *= -1

        # Fase según dirección (similar a LEFT/RIGHT del ESP32)
        if "IZQUIERDA" in gaze_direction:
            self.am_phase = -0.8
        elif "DERECHA" in gaze_direction:
            self.am_phase = 0.8
        else:
            self.am_phase = 0.0

    def draw_virtual_eyes(self, virtual_frame, left_ear, right_ear, gaze_direction, gaze_pos, left_brow_height=0.5, right_brow_height=0.5, for_video=False):
        """
        Dibuja los ojos virtuales según el modo seleccionado: rectángulos o ondas AM
        for_video: Si es True, no muestra parámetros (solo para grabación de video)
        """
        # Limpiar frame virtual
        virtual_frame.fill(0)
        
        # Calcular posición de los ojos virtuales basada en la mirada
        if for_video:
            # Para video: usar todo el ancho disponible (800px) sin sección de parámetros
            base_left_x = 200   # Ojo izquierdo centrado en la mitad izquierda
            base_right_x = 600  # Ojo derecho centrado en la mitad derecha
            base_y = 200        # Altura central
            movement_multiplier_x = 180  # Mayor rango de movimiento horizontal
            movement_multiplier_y = 120  # Mayor rango de movimiento vertical
        else:
            # Para visualización con parámetros: usar solo la parte izquierda (0-460px)
            base_left_x = 150   # Posición base ojo izquierdo
            base_right_x = 300  # Posición base ojo derecho (separación 150px)
            base_y = 200        # Altura central
            movement_multiplier_x = 120  # Amplificador horizontal: ±60px de movimiento
            movement_multiplier_y = 80   # Amplificador vertical: ±40px de movimiento
        
        virtual_left_x = int(base_left_x + (gaze_pos[0] - 0.5) * movement_multiplier_x)
        virtual_left_y = int(base_y + (gaze_pos[1] - 0.5) * movement_multiplier_y)
        virtual_right_x = int(base_right_x + (gaze_pos[0] - 0.5) * movement_multiplier_x)
        virtual_right_y = int(base_y + (gaze_pos[1] - 0.5) * movement_multiplier_y)
        
        # Color azul cian para ambos modos
        eye_color = (255, 255, 0)  # Azul cian en formato BGR
        
        # Definir variables de altura para ambos modos (para mostrar en parámetros)
        max_height = 100  # ALTURA VARIABLE: máxima escalada 50px * 2 = 100px
        min_height = 8    # ALTURA VARIABLE: mínima 8px cuando están completamente cerrados
        
        # Calcular altura base para ambos modos
        base_left_height = max(min_height, min(max_height, int((left_ear / 0.35) * max_height)))
        base_right_height = max(min_height, min(max_height, int((right_ear / 0.35) * max_height)))
        
        # Detectar estado de ojos para aplicar recorte por mitad (usado en ambos modos)
        eye_state = self.detect_eye_state(left_ear, right_ear)
        
        # Aplicar recorte por mitad según el estado de los ojos
        if self.both_eyes_closed or eye_state == "AMBOS_CERRADOS":
            left_height = base_left_height // 2
            right_height = base_right_height // 2
        elif self.left_winking or eye_state == "GUINANDO_IZQUIERDO":
            left_height = base_left_height // 2
            right_height = base_right_height
        elif self.right_winking or eye_state == "GUINANDO_DERECHO":
            left_height = base_left_height
            right_height = base_right_height // 2
        else:
            left_height = base_left_height
            right_height = base_right_height
        
        if self.visualization_mode == "AM":
            # === MODO AM TIPO ESP32: UNA SOLA ONDA GRANDE ===
            
            # Si no hay rostro (gaze_direction NO_DETECTADO) → ruido
            if gaze_direction == "NO_DETECTADO":
                # línea de ruido al estilo ESP32
                am_center_x = 230
                am_center_y = base_y
                am_width = 420
                prev_x = am_center_x - am_width // 2
                prev_y = am_center_y

                for i in range(am_width):
                    x = am_center_x - am_width // 2 + i
                    y = am_center_y + np.random.randint(-3, 4)
                    cv2.line(virtual_frame, (prev_x, prev_y), (x, y), eye_color, 1)
                    prev_x, prev_y = x, y
            else:
                # Centro horizontal de la zona de ojos (0-460 px)
                am_center_x = 230
                am_center_y = base_y  # 200 como ya tienes
                am_width = 420        # casi todo el ancho visible

                # APERTURA INDEPENDIENTE POR OJO: mapear cada EAR por separado
                # Mapear EAR típico (~0.15-0.35) a 0-100 para apertura de AM
                left_ear_openness = np.interp(left_ear, [0.15, 0.35], [0, 100])
                right_ear_openness = np.interp(right_ear, [0.15, 0.35], [0, 100])

                self.draw_am_wave(
                    virtual_frame,
                    am_center_x,
                    am_center_y,
                    left_ear_openness,   # Apertura ojo izquierdo
                    right_ear_openness,  # Apertura ojo derecho
                    self.am_phase,
                    am_width,
                    eye_color
                )
        
        elif self.visualization_mode == "REDONDEADOS":
            # === MODO REDONDEADOS: Rectángulos con esquinas redondeadas y solo diagonal superior ===
            rect_width = 80   # ANCHO CONSTANTE: 40px * 2 = 80px (NO cambia nunca)
            
            # Calcular coordenadas de los rectángulos (centrados en posición fija)
            # POSICIÓN: Solo controlada por dirección de mirada (gaze_pos)
            # TAMAÑO: Solo controlado por apertura de ojos (EAR)
            left_rect_x1 = virtual_left_x - rect_width // 2
            left_rect_y1 = virtual_left_y - left_height // 2
            left_rect_x2 = virtual_left_x + rect_width // 2
            left_rect_y2 = virtual_left_y + left_height // 2
            
            right_rect_x1 = virtual_right_x - rect_width // 2
            right_rect_y1 = virtual_right_y - right_height // 2
            right_rect_x2 = virtual_right_x + rect_width // 2
            right_rect_y2 = virtual_right_y + right_height // 2
            
            # Dibujar rectángulos redondeados con recorte diagonal superior únicamente
            self.draw_rounded_rectangle_with_cut(virtual_frame, left_rect_x1, left_rect_y1, left_rect_x2, left_rect_y2, 
                                               eye_color, left_brow_height, is_left_eye=True)
            self.draw_rounded_rectangle_with_cut(virtual_frame, right_rect_x1, right_rect_y1, right_rect_x2, right_rect_y2, 
                                               eye_color, right_brow_height, is_left_eye=False)
            
        else:
            # MODO RECTANGULOS: Dibujar rectángulos originales
            # TAMAÑO: Configuración de rectángulos (escalados al doble)
            rect_width = 80   # ANCHO CONSTANTE: 40px * 2 = 80px (NO cambia nunca)
            
            # Calcular coordenadas de los rectángulos (centrados en posición fija)
            # POSICIÓN: Solo controlada por dirección de mirada (gaze_pos)
            # TAMAÑO: Solo controlado por apertura de ojos (EAR)
            left_rect_x1 = virtual_left_x - rect_width // 2
            left_rect_y1 = virtual_left_y - left_height // 2
            left_rect_x2 = virtual_left_x + rect_width // 2
            left_rect_y2 = virtual_left_y + left_height // 2
            
            right_rect_x1 = virtual_right_x - rect_width // 2
            right_rect_y1 = virtual_right_y - right_height // 2
            right_rect_x2 = virtual_right_x + rect_width // 2
            right_rect_y2 = virtual_right_y + right_height // 2
            
            # Dibujar rectángulos con cortes diagonales en la parte superior
            self.draw_diagonal_rectangle(virtual_frame, left_rect_x1, left_rect_y1, left_rect_x2, left_rect_y2, 
                                       eye_color, left_brow_height, is_left_eye=True)
            self.draw_diagonal_rectangle(virtual_frame, right_rect_x1, right_rect_y1, right_rect_x2, right_rect_y2, 
                                       eye_color, right_brow_height, is_left_eye=False)
        
        # Solo mostrar parámetros si no es para video
        if not for_video:
            # Linea separadora entre visualizacion de ojos y parametros
            cv2.line(virtual_frame, (460, 0), (460, 400), (100, 100, 100), 2)
            
            # SECCION DE PARAMETROS: Area separada para informacion (derecha de la ventana)
            params_x_start = 480  # Inicio de la seccion de parametros
            params_y_start = 30   # Inicio vertical
            
            cv2.putText(virtual_frame, "=== PARAMETROS DEL SISTEMA ===", (params_x_start, params_y_start), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(virtual_frame, f"MODO: {self.visualization_mode}", (params_x_start, params_y_start + 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            cv2.putText(virtual_frame, f"MOVIMIENTO: {gaze_direction}", (params_x_start, params_y_start + 55), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            cv2.putText(virtual_frame, f"Pos X,Y: ({gaze_pos[0]:.2f}, {gaze_pos[1]:.2f})", (params_x_start, params_y_start + 80), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            
            cv2.putText(virtual_frame, "--- TAMANO (EAR) ---", (params_x_start, params_y_start + 110), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            cv2.putText(virtual_frame, f"Izq: {left_ear:.3f}", (params_x_start, params_y_start + 135), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            cv2.putText(virtual_frame, f"Der: {right_ear:.3f}", (params_x_start, params_y_start + 160), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            cv2.putText(virtual_frame, f"Alt Izq: {left_height}px", (params_x_start, params_y_start + 185), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            cv2.putText(virtual_frame, f"Alt Der: {right_height}px", (params_x_start, params_y_start + 210), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            
            cv2.putText(virtual_frame, "--- DIAGONAL (CEJAS) ---", (params_x_start, params_y_start + 240), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 100), 1)
            cv2.putText(virtual_frame, f"Izq: {left_brow_height:.2f}", (params_x_start, params_y_start + 265), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 100), 1)
            cv2.putText(virtual_frame, f"Der: {right_brow_height:.2f}", (params_x_start, params_y_start + 290), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 100), 1)
            
            cv2.putText(virtual_frame, "--- PARPADEOS ---", (params_x_start, params_y_start + 320), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 100, 100), 1)
            cv2.putText(virtual_frame, f"Izq: {self.left_blink_total}", (params_x_start, params_y_start + 345), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 100, 100), 1)
            cv2.putText(virtual_frame, f"Der: {self.right_blink_total}", (params_x_start, params_y_start + 370), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 100, 100), 1)
            
            # Información de estado de ojos
            eye_state = "NORMAL"
            if self.both_eyes_closed:
                eye_state = "AMBOS CERRADOS"
            elif self.left_winking:
                eye_state = "GUINANDO IZQ"
            elif self.right_winking:
                eye_state = "GUINANDO DER"
            else:
                eye_state = "ABIERTOS"
                
            cv2.putText(virtual_frame, f"Estado: {eye_state}", (params_x_start, params_y_start + 395), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 255, 255), 1)
        
        return virtual_frame
    
    def draw_rounded_rectangle_with_cut(self, frame, x1, y1, x2, y2, color, brow_height, is_left_eye=False):
        """
        Dibuja un rectángulo con esquinas redondeadas y ÚNICAMENTE recorte diagonal superior según la altura de las cejas
        is_left_eye: True para ojo izquierdo (diagonal hacia la derecha), False para ojo derecho (diagonal hacia la izquierda)
        
        CARACTERÍSTICAS DEL NUEVO MODO REDONDEADOS:
        - ESQUINAS REDONDEADAS: Radio de curvatura fijo para suavizar el rectángulo
        - RECORTE DIAGONAL: Solo en la parte superior (no hay diagonal interna como en modo RECTANGULOS)
        - POSICIÓN: Las coordenadas x1,y1,x2,y2 vienen del movimiento de mirada
        - TAMAÑO: Las coordenadas reflejan el tamaño calculado por EAR
        - DIAGONAL: Controlada ÚNICAMENTE por brow_height (posición de cejas)
        """
        # Calcular intensidad del corte diagonal basado ÚNICAMENTE en altura de cejas
        # brow_height: 0.0 = cejas bajas (menos corte), 1.0 = cejas altas (más corte)
        diagonal_cut = int(brow_height * 30)  # Máximo 30px de corte diagonal
        
        # Radio para esquinas redondeadas (fijo)
        corner_radius = 15
        
        # Crear máscara para el rectángulo redondeado con recorte diagonal
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        
        # Definir puntos del polígono con recorte diagonal superior
        if is_left_eye:
            # Ojo izquierdo: diagonal de derecha-arriba a izquierda-abajo
            cut_points = np.array([
                [x1, y2],                           # Esquina inferior izquierda
                [x2, y2],                           # Esquina inferior derecha
                [x2 - diagonal_cut, y1],            # Esquina superior derecha (con corte)
                [x1, y1 + diagonal_cut],            # Esquina superior izquierda (con corte)
            ], np.int32)
        else:
            # Ojo derecho: diagonal de izquierda-arriba a derecha-abajo
            cut_points = np.array([
                [x1, y2],                           # Esquina inferior izquierda
                [x2, y2],                           # Esquina inferior derecha
                [x2, y1 + diagonal_cut],            # Esquina superior derecha (con corte)
                [x1 + diagonal_cut, y1],            # Esquina superior izquierda (con corte)
            ], np.int32)
        
        # Crear el polígono básico con el recorte
        cv2.fillPoly(mask, [cut_points], 255)
        
        # Aplicar suavizado para crear efecto de esquinas redondeadas
        # Usamos un kernel circular para suavizar las esquinas
        kernel_size = min(corner_radius * 2 + 1, 31)  # Limitar el tamaño del kernel
        if kernel_size % 2 == 0:
            kernel_size += 1  # Asegurar que sea impar
            
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        
        # Aplicar erosión seguida de dilatación para suavizar esquinas
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.GaussianBlur(mask, (kernel_size, kernel_size), 0)
        
        # Crear imagen temporal con el color del ojo
        temp_img = np.zeros_like(frame)
        temp_img[:, :] = color
        
        # Aplicar la máscara con antialiasing
        mask_normalized = mask.astype(np.float32) / 255.0
        for c in range(3):
            frame[:, :, c] = frame[:, :, c] * (1 - mask_normalized) + temp_img[:, :, c] * mask_normalized
        
        # Dibujar contorno suavizado
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            cv2.drawContours(frame, contours, -1, color, 2)
    
    def draw_diagonal_rectangle(self, frame, x1, y1, x2, y2, color, brow_height, is_left_eye=False):
        """
        Dibuja un rectángulo con corte diagonal en la parte superior según la altura de las cejas
        is_left_eye: True para ojo izquierdo (diagonal hacia la derecha), False para ojo derecho (diagonal hacia la izquierda)
        
        VERIFICACIÓN DE FUNCIONALIDAD:
        - DIAGONAL: Controlada ÚNICAMENTE por brow_height (posición de cejas)
        - POSICIÓN: Las coordenadas x1,y1,x2,y2 vienen del movimiento de mirada
        - TAMAÑO: Las coordenadas reflejan el tamaño calculado por EAR
        """
        # DIAGONAL: Calcular intensidad del corte diagonal basado ÚNICAMENTE en altura de cejas
        # brow_height: 0.0 = cejas bajas (menos corte), 1.0 = cejas altas (más corte)
        diagonal_cut = int(brow_height * 30)  # Máximo 30px de corte diagonal
        
        # Puntos del polígono según el ojo (simetría)
        if is_left_eye:
            # Ojo izquierdo: diagonal de derecha-arriba a izquierda-abajo
            points = np.array([
                [x1, y2],                           # Esquina inferior izquierda
                [x2, y2],                           # Esquina inferior derecha
                [x2 - diagonal_cut, y1],            # Esquina superior derecha (con corte)
                [x1, y1 + diagonal_cut],            # Esquina superior izquierda (con corte)
            ], np.int32)
        else:
            # Ojo derecho: diagonal de izquierda-arriba a derecha-abajo
            points = np.array([
                [x1, y2],                           # Esquina inferior izquierda
                [x2, y2],                           # Esquina inferior derecha
                [x2, y1 + diagonal_cut],            # Esquina superior derecha (con corte)
                [x1 + diagonal_cut, y1],            # Esquina superior izquierda (con corte)
            ], np.int32)
        
        # Dibujar polígono relleno
        cv2.fillPoly(frame, [points], color)
        
        # Dibujar borde
        cv2.polylines(frame, [points], True, color, 2)

    def process_frame(self, frame):
        """
        Procesa un frame para detectar rostro, ojos y movimientos
        """
        # Convertir BGR a RGB para MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)
        
        # Variables por defecto
        left_ear = 0.3
        right_ear = 0.3
        gaze_direction = "NO_DETECTADO"
        gaze_pos = (0.5, 0.5)
        left_brow_height = 0.5
        right_brow_height = 0.5
        
        if results.multi_face_landmarks:
            # Obtener el rostro más próximo (el primero detectado)
            face_landmarks = results.multi_face_landmarks[0]
            
            # Extraer landmarks de los ojos
            landmarks = face_landmarks.landmark
            
            # Obtener landmarks de ojos izquierdo y derecho
            left_eye_landmarks = [landmarks[i] for i in self.LEFT_EYE_CONTOUR]
            right_eye_landmarks = [landmarks[i] for i in self.RIGHT_EYE_CONTOUR]
            
            # Obtener landmarks de cejas
            left_eyebrow_landmarks = [landmarks[i] for i in self.LEFT_EYEBROW]
            right_eyebrow_landmarks = [landmarks[i] for i in self.RIGHT_EYEBROW]
            
            # Calcular EAR para detección de parpadeo
            left_ear = self.calculate_eye_aspect_ratio(left_eye_landmarks, frame.shape)
            right_ear = self.calculate_eye_aspect_ratio(right_eye_landmarks, frame.shape)
            
            # Calcular altura de cejas
            left_brow_height = self.get_eyebrow_height(left_eyebrow_landmarks, left_eye_landmarks, frame.shape)
            right_brow_height = self.get_eyebrow_height(right_eyebrow_landmarks, right_eye_landmarks, frame.shape)
            
            # Detectar estado de ojos (guiños, ambos cerrados, etc.)
            eye_state = self.detect_eye_state(left_ear, right_ear)
            
            # Detectar parpadeos
            if left_ear < self.blink_threshold:
                self.left_blink_counter += 1
            else:
                if self.left_blink_counter >= self.consecutive_frames:
                    self.left_blink_total += 1
                self.left_blink_counter = 0
            
            if right_ear < self.blink_threshold:
                self.right_blink_counter += 1
            else:
                if self.right_blink_counter >= self.consecutive_frames:
                    self.right_blink_total += 1
                self.right_blink_counter = 0
            
            # Obtener centros de los ojos para tracking de movimiento
            left_eye_full = [landmarks[i] for i in self.LEFT_EYE_LANDMARKS]
            right_eye_full = [landmarks[i] for i in self.RIGHT_EYE_LANDMARKS]
            
            left_center = self.get_eye_center(left_eye_full, frame.shape)
            right_center = self.get_eye_center(right_eye_full, frame.shape)
            
            # Detectar dirección de mirada con detección mejorada
            gaze_direction, gaze_pos = self.detect_eye_movement(left_center, right_center, frame.shape, landmarks)
            
            # === VISUALIZACIÓN COMPLETA DE LANDMARKS FACIALES CON CONEXIONES ===
            
            # Dibujar TODAS las conexiones de Face Mesh (patrón completo de polígonos)
            self.mp_drawing.draw_landmarks(
                frame,
                face_landmarks,
                self.mp_face_mesh.FACEMESH_TESSELATION,  # Todas las conexiones internas
                None,
                self.mp_drawing_styles.get_default_face_mesh_tesselation_style()
            )
            
            # Dibujar contornos principales por encima
            self.mp_drawing.draw_landmarks(
                frame,
                face_landmarks,
                self.mp_face_mesh.FACEMESH_CONTOURS,
                None,
                self.mp_drawing_styles.get_default_face_mesh_contours_style()
            )
            
            # Dibujar contornos de iris para mayor detalle
            self.mp_drawing.draw_landmarks(
                frame,
                face_landmarks,
                self.mp_face_mesh.FACEMESH_IRISES,
                None,
                self.mp_drawing_styles.get_default_face_mesh_iris_connections_style()
            )
            
            # === PUNTOS ROJOS DE LANDMARKS SUPERPUESTOS ===
            h, w = frame.shape[:2]
            
            # Dibujar todos los landmarks como puntos rojos pequeños encima de las líneas
            for landmark in landmarks:
                x = int(landmark.x * w)
                y = int(landmark.y * h)
                cv2.circle(frame, (x, y), 2, (0, 0, 255), -1)  # Puntos rojos
            
            # Destacar landmarks de ojos con puntos más grandes (rojo-naranja)
            for i in self.LEFT_EYE_CONTOUR + self.RIGHT_EYE_CONTOUR:
                x = int(landmarks[i].x * w)
                y = int(landmarks[i].y * h)
                cv2.circle(frame, (x, y), 4, (0, 100, 255), -1)  # Rojo-naranja para ojos
            
            # Destacar contorno de cara
            face_contour = [10, 151, 9, 8, 168, 6, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
            for i in face_contour:
                if i < len(landmarks):
                    x = int(landmarks[i].x * w)
                    y = int(landmarks[i].y * h)
                    cv2.circle(frame, (x, y), 3, (0, 50, 255), -1)  # Rojo más oscuro para contorno
            
            # Marcar centros de ojos con círculos verdes y amarillos
            cv2.circle(frame, left_center, 8, (0, 255, 255), 2)   # Amarillo para centros
            cv2.circle(frame, right_center, 8, (0, 255, 255), 2)
            cv2.circle(frame, left_center, 5, (0, 255, 0), -1)    # Verde sólido en el centro
            cv2.circle(frame, right_center, 5, (0, 255, 0), -1)
            
            # === INFORMACIÓN TEXTUAL MEJORADA ===
            cv2.putText(frame, f"MALLA FACIAL COMPLETA - PATRON DE POLIGONOS", (10, 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(frame, f"Landmarks: {len(landmarks)} | Conexiones: Teselacion", (10, 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, f"Dir: {gaze_direction}", (10, 75), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            cv2.putText(frame, f"EAR_L: {left_ear:.3f}", (10, 100), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            cv2.putText(frame, f"EAR_R: {right_ear:.3f}", (10, 125), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            cv2.putText(frame, f"Ceja_L: {left_brow_height:.2f}", (10, 150), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 255), 1)
            cv2.putText(frame, f"Ceja_R: {right_brow_height:.2f}", (10, 175), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 255), 1)
        
        else:
            # === SIN DETECCIÓN FACIAL ===
            cv2.putText(frame, "SIN DETECCION FACIAL", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            cv2.putText(frame, "Posiciona tu rostro frente a la camara", (10, 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        
        return frame, left_ear, right_ear, gaze_direction, gaze_pos, left_brow_height, right_brow_height

    def run_virtual_eye_tracker(self):
        """
        Ejecuta el sistema completo de seguimiento ocular con vista virtual
        """
        # Inicializar captura de video
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print("Error: No se pudo acceder a la cámara")
            return
        
        # Configurar resolución
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Crear ventana virtual ampliada (800x400 para separar visualizacion de parametros)
        virtual_frame = np.zeros((400, 800, 3), dtype=np.uint8)
        
        # Crear ventana separada para escaneo facial (como en simple_eye_tracker)
        face_scan_frame = np.ones((480, 640, 3), dtype=np.uint8) * 255
        
        print("Sistema de seguimiento ocular iniciado.")
        print("Ventanas: Principal (malla completa), Virtual (emulacion), Escaneo Facial (patron poligonos)")
        print("NUEVA CARACTERISTICA: Patron completo de poligonos cubriendo todo el rostro")
        print("Controles:")
        print("- 'q': Salir")
        print("- 'r': Resetear contadores de parpadeo")
        print("- 'c': Limpiar historial de movimientos")
        print("- 'm': Cambiar modo de visualizacion (RECTANGULOS/REDONDEADOS/AM)")
        print("- 'g': Iniciar grabacion de animacion")
        print("- 'p': Parar grabacion y guardar archivo")
        
        # Variables para FPS
        prev_time = time.time()
        fps_counter = 0
        fps_display = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: No se pudo capturar el frame")
                break
            
            # Voltear horizontalmente para efecto espejo
            frame = cv2.flip(frame, 1)
            
            # === CREAR VENTANA DE ESCANEO FACIAL INDEPENDIENTE ===
            # Crear frame separado para escaneo facial (solo landmarks) con fondo blanco
            face_scan_frame = np.ones_like(frame) * 255
            
            # Procesar frame para detección ocular
            processed_frame, left_ear, right_ear, gaze_direction, gaze_pos, left_brow_height, right_brow_height = self.process_frame(frame.copy())
            
            # === CREAR VISUALIZACIÓN DE ESCANEO FACIAL ===
            # Convertir frame a RGB para MediaPipe (solo para escaneo)
            rgb_frame_scan = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results_scan = self.face_mesh.process(rgb_frame_scan)
            
            if results_scan.multi_face_landmarks:
                face_landmarks_scan = results_scan.multi_face_landmarks[0]
                landmarks_scan = face_landmarks_scan.landmark
                h, w = frame.shape[:2]
                
                # === DIBUJAR PATRÓN COMPLETO DE POLÍGONOS EN VENTANA DE ESCANEO ===
                # Dibujar TODAS las conexiones de Face Mesh (teselación completa)
                self.mp_drawing.draw_landmarks(
                    face_scan_frame,
                    face_landmarks_scan,
                    self.mp_face_mesh.FACEMESH_TESSELATION,  # Conexiones internas completas
                    None,
                    self.mp_drawing_styles.get_default_face_mesh_tesselation_style()
                )
                
                # Dibujar contornos principales
                self.mp_drawing.draw_landmarks(
                    face_scan_frame,
                    face_landmarks_scan,
                    self.mp_face_mesh.FACEMESH_CONTOURS,
                    None,
                    self.mp_drawing_styles.get_default_face_mesh_contours_style()
                )
                
                # Dibujar iris
                self.mp_drawing.draw_landmarks(
                    face_scan_frame,
                    face_landmarks_scan,
                    self.mp_face_mesh.FACEMESH_IRISES,
                    None,
                    self.mp_drawing_styles.get_default_face_mesh_iris_connections_style()
                )
                
                # Dibujar TODOS los landmarks como puntos rojos encima de las líneas
                for landmark in landmarks_scan:
                    x = int(landmark.x * w)
                    y = int(landmark.y * h)
                    cv2.circle(face_scan_frame, (x, y), 2, (0, 0, 255), -1)  # Puntos rojos brillantes
                
                # Añadir puntos más grandes para ojos
                for i in self.LEFT_EYE_CONTOUR + self.RIGHT_EYE_CONTOUR:
                    x = int(landmarks_scan[i].x * w)
                    y = int(landmarks_scan[i].y * h)
                    cv2.circle(face_scan_frame, (x, y), 4, (0, 100, 255), -1)  # Rojo-naranja para ojos
                
                # Calcular y marcar centros de ojos
                left_eye_points = [(int(landmarks_scan[i].x * w), int(landmarks_scan[i].y * h)) 
                                  for i in self.LEFT_EYE_CONTOUR]
                right_eye_points = [(int(landmarks_scan[i].x * w), int(landmarks_scan[i].y * h)) 
                                   for i in self.RIGHT_EYE_CONTOUR]
                
                left_center_scan = (sum(p[0] for p in left_eye_points) // len(left_eye_points),
                                   sum(p[1] for p in left_eye_points) // len(left_eye_points))
                right_center_scan = (sum(p[0] for p in right_eye_points) // len(right_eye_points),
                                    sum(p[1] for p in right_eye_points) // len(right_eye_points))
                
                # Marcar centros con círculos amarillos
                cv2.circle(face_scan_frame, left_center_scan, 8, (0, 255, 255), 2)
                cv2.circle(face_scan_frame, right_center_scan, 8, (0, 255, 255), 2)
                
                # Información en ventana de escaneo
                cv2.putText(face_scan_frame, "MALLA FACIAL COMPLETA - PATRON DE POLIGONOS", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                cv2.putText(face_scan_frame, f"Landmarks: {len(landmarks_scan)} | Conexiones: Completas", (10, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                cv2.putText(face_scan_frame, "Teselacion + Contornos + Iris", (10, 85), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 100), 1)
            else:
                # Sin detección en ventana de escaneo
                cv2.putText(face_scan_frame, "SIN DETECCION FACIAL", (100, 200), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                cv2.putText(face_scan_frame, "Posiciona tu rostro frente a la camara", (50, 250), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
            
            # Detectamos si hay rostro (client_detected ≈ BLE conectado)
            client_detected = (gaze_direction != "NO_DETECTADO")
            # Actualizar estado AM (apertura + fase)
            self.update_am_state(client_detected, gaze_direction)
            
            # Crear visualización virtual
            virtual_frame = self.draw_virtual_eyes(virtual_frame.copy(), left_ear, right_ear, gaze_direction, gaze_pos, left_brow_height, right_brow_height)
            
            # Capturar frame para grabación si está activa (después de crear virtual_frame)
            self.capture_frame_for_recording(left_ear, right_ear, gaze_direction, gaze_pos, left_brow_height, right_brow_height, virtual_frame)
            
            # Calcular FPS
            fps_counter += 1
            current_time = time.time()
            if current_time - prev_time >= 1.0:
                fps_display = fps_counter
                fps_counter = 0
                prev_time = current_time
            
            # Mostrar FPS
            cv2.putText(processed_frame, f"FPS: {fps_display}", (10, frame.shape[0] - 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # Mostrar frames
            cv2.imshow('Eye Tracker - Vista Principal', processed_frame)
            cv2.imshow('Eye Tracker - Emulador Virtual', virtual_frame)
            cv2.imshow('ESCANEO FACIAL - Landmarks en Tiempo Real', face_scan_frame)
            
            # Manejar teclas
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):
                self.left_blink_total = 0
                self.right_blink_total = 0
                print("Contadores de parpadeo reseteados")
            elif key == ord('c'):
                self.eye_movement_history.clear()
                print("Historial de movimientos limpiado")
            elif key == ord('m') or key == ord('M'):
                # Ciclar entre los 3 modos de visualización
                if self.visualization_mode == "RECTANGULOS":
                    self.visualization_mode = "REDONDEADOS"
                    print("Modo cambiado a: RECTANGULOS REDONDEADOS")
                elif self.visualization_mode == "REDONDEADOS":
                    self.visualization_mode = "AM"
                    print("Modo cambiado a: ONDAS AM")
                else:
                    self.visualization_mode = "RECTANGULOS"
                    print("Modo cambiado a: RECTANGULOS")
            elif key == ord('g') or key == ord('G'):
                # Iniciar grabación
                self.start_recording()
            elif key == ord('p') or key == ord('P'):
                # Parar grabación
                self.stop_recording()
        
        # Limpieza
        cap.release()
        cv2.destroyAllWindows()
        print("Sistema de seguimiento ocular terminado")

def main():
    """
    Función principal del programa
    """
    print("=== EMULADOR DE VISTA VIRTUAL EN TIEMPO REAL ===")
    print("Alejandro Aguirre Diaz 23110162")
    print()
    print("Inicializando sistema de seguimiento ocular...")
    
    try:
        # Crear instancia del tracker
        eye_tracker = EyeTracker()
        
        # Ejecutar sistema
        eye_tracker.run_virtual_eye_tracker()
        
    except Exception as e:
        print(f"Error inesperado: {str(e)}")
        print("Verifique que la camara este conectada y funcionando correctamente")

if __name__ == "__main__":
    main()