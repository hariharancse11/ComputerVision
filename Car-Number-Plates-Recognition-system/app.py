# Imports
from flask import Flask, render_template, Response, request
import cv2
import easyocr
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime,timedelta
# Function to save plate to the database
from sqlalchemy import and_

app = Flask(__name__)

# Replace video_path with your video file path or use webcam (0)
video_path = 'demo.mp4'
camera = cv2.VideoCapture(video_path)
# Define the database model
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///car_plate.db'
db = SQLAlchemy(app)

harcascade = "model/haarcascade_russian_plate_number.xml"
reader = easyocr.Reader(['en'])
min_area = 500
count = 0

# Generate video frames
def generate_frames():
    global count
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            plate_cascade = cv2.CascadeClassifier(harcascade)
            img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            plates = plate_cascade.detectMultiScale(img_gray, 1.1, 4)

            for (x, y, w, h) in plates:
                area = w * h
                if area > min_area:
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
                    img_roi = frame[y: y + h, x: x + w]

                    # Process the number plate with EasyOCR
                    output = reader.readtext(img_roi)
                    actual_text = "Number Plate"
                    if output:
                        text_confidence = output[0][2]
                        if text_confidence >= 0.85:
                            actual_text = output[0][1]
                            save_plate(actual_text)  # Save plate to database

                    cv2.putText(frame, actual_text, (x, y - 5), cv2.FONT_HERSHEY_COMPLEX_SMALL, 1, (255, 0, 255), 2)

            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')



class CarPlate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate_number = db.Column(db.String(20))
    date_recorded = db.Column(db.DateTime, default=datetime.utcnow)

# Create the database tables
with app.app_context():
    db.create_all()


# Function to save plate to the database with a time constraint
def save_plate(plate_number):
    plate_number = plate_number.replace('-','')
    plate_number = plate_number.replace(' ','')
    import re

    # Your regex pattern
    # pattern = r'^(?:[A-Za-z])?(?:\d{3})?(?:[A-Za-z]{2})?$'
    pattern = r'^[A-Za-z0-9-]*$'
    def has_number(input_string):
        return bool(re.search(r'\d', input_string))
    if re.match(pattern, plate_number) and has_number(plate_number):
        with app.app_context():
            now = datetime.utcnow()
            time_constraint = now - timedelta(minutes=10)  # Define the time constraint (1 hour ago)

            # Check if a record for the plate number exists within the time constraint
            existing_record = CarPlate.query.filter(
                and_(
                    CarPlate.plate_number == plate_number,
                    CarPlate.date_recorded >= time_constraint,
                    CarPlate.date_recorded < now
                )
            ).first()

            if existing_record:
                print('Plate number was already recognized within the last 10 minutes.')
                return  # Do not save if the plate number was recognized within the last hour

            # Save the plate number as it has not been recognized within the last hour
            new_car_plate = CarPlate(plate_number=plate_number)
            try:
                db.session.add(new_car_plate)
                db.session.commit()
                print('Car plate number saved!')
            except Exception as e:
                print(f'Error saving car plate number: {str(e)}')



# Flask routes for web interface
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/view', methods=['GET', 'POST'])
def view_by_date():
    if request.method == 'POST':
        date_input = request.form['date_input']
        try:
            date = datetime.strptime(date_input, '%Y-%m-%d').date()
            car_plates = CarPlate.query.filter_by(date_recorded=date).all()
            return render_template('view.html', car_plates=car_plates)
        except ValueError:
            return 'Invalid date format. Please use YYYY-MM-DD.'
    else:
        return render_template('date_input.html')

@app.route('/view_data')
def view_data():
    car_plates = CarPlate.query.all()
    return render_template('view_data.html', car_plates=car_plates)

@app.route('/clear', methods=['GET', 'POST'])
def clear_car_plate_table():
    with app.app_context():
        try:
            db.session.query(CarPlate).delete()
            db.session.commit()
            return('CarPlate table cleared!')
        except Exception as e:
            db.session.rollback()
            return(f'Error clearing CarPlate table: {str(e)}')

if __name__ == "__main__":
    app.run(debug=True)
    camera.release()
    cv2.destroyAllWindows()
