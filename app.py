import os
import pickle
from datetime import datetime
import face_recognition
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, Response, flash, session
import cv2
import firebase_admin
from firebase_admin import credentials, storage, db

app = Flask(__name__)
app.secret_key = 'fyp1facerecognitionattendancesystem'

# Load the Firebase credentials
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': "https://fyp1-d54dc-default-rtdb.asia-southeast1.firebasedatabase.app/",
    'storageBucket': "fyp1-d54dc.appspot.com"
})


@app.route('/')
def index():
    # Clear the session data
    session.clear()
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Get the form data
        username = request.form['username']
        password = request.form['password']

        # Check the credentials
        # TODO: ADD DATABASE
        if username == 'admin' and password == 'adminadmin':
            # Set the session userid
            session['userid'] = username
            # Redirect to the attendance page
            return redirect(url_for('dashboard'))
        else:
            # Redirect back to the login page
            return redirect(url_for('login'))
    else:
        # Render the login template
        return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/start_attendance')
def start_attendance():
    return render_template('start_attendance.html')


@app.route('/register_new_user', methods=['GET', 'POST'])
def register_new_user():
    if request.method == 'POST':

        # Get the form data from the request
        user_type = request.form['user_type']
        name = request.form['name']
        id = request.form['id']
        password = request.form['password']
        image = request.files['image']

        # TODO: comment this if not needed for validation
        # Save the image to a temporary location
        image.save('static/Images/tmp.jpg')

        # Get a reference to the storage bucket and create a blob
        bucket = storage.bucket()
        blob = bucket.blob(f'{user_type}/{id}/{id}.jpg')

        # Upload the image to the blob
        image.seek(0)
        blob.upload_from_file(image)

        # Add the user data to the Realtime Database
        ref = db.reference(user_type)
        ref.child(id).set({
            'name': name,
            'password': password,
            'image_url': blob.public_url
        })

        # Redirect to the success page
        return redirect(url_for('register_success'))
    else:
        # Render the register form template
        return render_template('register_new_user.html')


@app.route('/register_success')
def register_success():
    return render_template('register_success.html')


@app.route('/train_model', methods=['GET', 'POST'])
def train_model():
    if request.method == 'POST':
        # Get a reference to the bucket
        bucket = storage.bucket()

        # Loop through the lecturer and student folders
        for user_type in ['lecturer', 'student']:
            encodings = []

            # Get a reference from the realtime database
            collection_ref = db.reference(user_type).get()

            # Loop through the documents in the collection
            for id, data in collection_ref.items():
                # Get the image blob from the storage
                image_blob = bucket.get_blob(f'{user_type}/{id}/{id}.jpg')

                # Skip processing if the image blob is None
                if image_blob is None:
                    continue

                # Read the image data as an array using cv2
                image_array = np.frombuffer(image_blob.download_as_string(), np.uint8)
                image = cv2.imdecode(image_array, cv2.COLOR_BGRA2BGR)

                # Pass the image array to the generate_encodings function
                encoding = generate_encodings([image])
                if not encoding:
                    flash(f"No face detected for {user_type} : {id}", "danger")

                # Add the id and encoding to the encodings list
                encodings.append([id, encoding])

            # Serialize the encoding list and name it with the user_type
            serialized_encoding = pickle.dumps(encodings)
            serialized_file = f'pickle/{user_type}.pkl'

            # Upload the serialized encoding list to the storage
            bucket.blob(serialized_file).upload_from_string(serialized_encoding)

            # Update the last trained time in the Realtime Database for each id
            current_time = datetime.now()
            formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
            for id in encodings:
                db.reference(user_type).child(id[0]).update({
                    'last_trained_time': formatted_time
                })

        return 'Training Complete'

    else:
        # Return the train_model template
        return render_template('train_model.html')


@app.route('/video_feed')
def video_feed():
    # Return the video stream response generated by the record_attendance function
    return Response(record_attendance(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


def record_attendance():
    # Open the webcam
    cap = cv2.VideoCapture(0)

    # Set to 1280x720
    cap.set(3, 1280)
    cap.set(4, 720)

    # Keep capturing frames until the program is interrupted
    while True:
        # Capture a frame from the webcam
        success, frame = cap.read()

        # Resize frame to 25%
        resized_frame = cv2.resize(frame, (0, 0), None, 0.25, 0.25)

        # Convert color space from BGR to RGB
        resized_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)

        face_location = face_recognition.face_locations(resized_frame)
        encoded_frame = face_recognition.face_encodings(resized_frame, face_location)

        for face_encode, face_location in zip(encoded_frame, face_location):
            # TODO: Pass in ENCODE_LIST_KNOWN after generating encodings from the list of files
            matches = face_recognition.compare_faces(ENCODE_LIST_KNOWN, face_encode)
            distance = face_recognition.face_distance(ENCODE_LIST_KNOWN, face_encode)

            match_index = np.argmin(distance)

            if matches[match_index]:
                pass  # TODO: from youtube video

        # Encode the frame in JPEG format
        ret, jpeg = cv2.imencode('.jpg', frame)

        # Return the frame as a response
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

    cap.release()


def generate_encodings(image_list):
    encode_list = []
    for image in image_list:
        # Convert color space from BGR to RGB
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Calculate the 128-dimensional face encodings for the first face detected
        encode = face_recognition.face_encodings(image)
        if encode:
            encode_list.append(encode[0])

    return encode_list


if __name__ == '__main__':
    app.run(debug=True, threaded=True)
