from PyQt5.QtGui import QPixmap
import sounddevice as sd
import soundfile as sf
import librosa as lb
import numpy as np
from numpy import mean, var
from sklearn.ensemble import RandomForestClassifier
import warnings


class ApplicationManger:
    def __init__(self, ui):
        self.ui = ui
        self.recorded_voice = None
        self.pass_sentences_progress_bars = [ui.Grant_Me_Access_ProgressBar, ui.Open_Middle_Door_ProgressBar,
                                             ui.Release_Entrance_Key_ProgressBar]
        self.people_progress_bars = [ui.Hazem_ProgressBar, ui.Omar_ProgressBar, ui.Ahmed_ProgressBar,
                                     ui.Youssef_ProgressBar]
        self.people_check_boxes = [ui.Hazem_CheckBox, ui.Omar_CheckBox, ui.Ahmed_CheckBox, ui.Youssef_CheckBox]
        self.features_array = None
        self.database_features_array = []
        self.file_names = []
        self.c = 1
        self.right_mark_icon = QPixmap("Assets/Correct.png").scaledToWidth(60)
        self.wrong_mark_icon = QPixmap("Assets/Wrong.png").scaledToWidth(60)
        self.icons = [[self.wrong_mark_icon, "Denied"], [self.right_mark_icon, "Authorized"]]
    
    def create_database(self):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            for name in ("Hazem", "Omar", "Taha", "Youssef"):
                for word in ("Access", "Door", "key"):
                    for i in range(1, 31):
                        self.calculate_sound_features(f"Voice Dataset/{name}_{word} ({i}).ogg")

    @staticmethod
    def calculate_mean_var(data):
        return [d.mean() for d in data], [d.var() for d in data]

    def calculate_sound_features(self, file_path, database_flag=True):
        log_mel_spectrogram_mean = []
        log_mel_spectrogram_var = []
        mfccs_mean = []
        mfccs_var = []
        cqt_mean = []
        cqt_var = []
        chroma_mean = []
        chroma_var = []
        tone_mean = []
        tone_var = []

        voice_data, sampling_frequency = lb.load(file_path)
        mfccs = lb.feature.mfcc(y=voice_data, sr=sampling_frequency, n_fft=1024, hop_length=512, n_mels=13)
        chroma = lb.feature.chroma_stft(y=voice_data, sr=sampling_frequency, n_fft=1024, hop_length=512)
        log_mel_spectrogram = lb.power_to_db(
            lb.feature.melspectrogram(y=voice_data, sr=sampling_frequency, n_fft=1024, hop_length=512, n_mels=13))
        constant_q_transform = np.abs(lb.cqt(y=voice_data, sr=sampling_frequency))
        tone = lb.feature.tonnetz(y=voice_data, sr=sampling_frequency)
        spectral_bandwidth = lb.feature.spectral_bandwidth(y=voice_data, sr=sampling_frequency,
                                                           n_fft=1024, hop_length=512)
        amplitude_envelope = self.calculate_amplitude_envelope(voice_data, 1024, 512)
        root_mean_square = lb.feature.rms(y=voice_data, frame_length=1024, hop_length=512)
        filename = file_path[14:23]

        features = [log_mel_spectrogram, mfccs, constant_q_transform, chroma, tone]
        features_mean = [log_mel_spectrogram_mean, mfccs_mean, cqt_mean, chroma_mean, tone_mean]
        features_var = [log_mel_spectrogram_var, mfccs_var, cqt_var, chroma_var, tone_var]
        for i in range(len(features)):
            features_mean[i], features_var[i] = self.calculate_mean_var(features[i])

        self.features_array = np.hstack((mean(amplitude_envelope), var(amplitude_envelope), mean(root_mean_square),
                                        var(root_mean_square), mean(spectral_bandwidth), var(spectral_bandwidth),
                                        tone_mean, tone_var, chroma_mean, chroma_var, cqt_mean, cqt_var, mfccs_mean,
                                        mfccs_var, log_mel_spectrogram_mean, log_mel_spectrogram_var))
        
        if database_flag:
            self.database_features_array.append(self.features_array)
            self.file_names.append(filename)

    def train_model(self):

        rf_classifier = RandomForestClassifier(n_estimators=300, criterion="entropy", bootstrap=True, warm_start=True,
                                               random_state=42)
        result = rf_classifier.fit(self.database_features_array, self.file_names)
        return result

    def record_voice(self):
        duration = 3  # seconds
        self.recorded_voice = sd.rec(frames=int(44100*duration), samplerate=44100,
                                     channels=1, blocking=True, dtype='int16')
        sf.write("output.ogg", self.recorded_voice, 44100)
        self.recorded_voice, sampling_frequency = lb.load("output.ogg")
        self.ui.Spectrogram.canvas.plot_spectrogram(self.recorded_voice, sampling_frequency)
        
        # print(f"Omar_Access ({self.c}).ogg")
        # self.c += 1
        self.calculate_sound_features("output.ogg", False)
        model = self.train_model()
        rf_probabilities = model.predict_proba(self.features_array.reshape(1, -1))
        self.check_matching(rf_probabilities[0])

    def check_matching(self, probs):
        statement_sums = []
        people_sums = []
        for i in range(3):
            probabilities_sum = 0
            for j in range(4):
                probabilities_sum += probs[i + j*3]
            statement_sums.append(probabilities_sum)
            self.pass_sentences_progress_bars[i].setValue(int(probabilities_sum*100))

        for i in range(4):
            probabilities_sum = 0
            for j in range(3):
                probabilities_sum += probs[i*3 + j]
            people_sums.append(probabilities_sum)
            self.people_progress_bars[i].setValue(int(probabilities_sum*100))

        self.verify_sound(statement_sums, people_sums)
        
    def verify_sound(self, statement_sums, people_sums):
        access_flag = 0
        if self.ui.Security_Voice_Code_RadioButton.isChecked():
            if max(statement_sums) > 0.4:
                access_flag = 1
        else:
            for i in range(4):
                if (max(people_sums) == people_sums[i] and max(statement_sums) > 0.5
                        and self.people_check_boxes[i].isChecked()):
                    access_flag = 1

        self.set_icon(access_flag)

    def set_icon(self, flag):
        self.ui.Access_Icon_Label.setPixmap(self.icons[flag][0])
        self.ui.Access_Label.setText(f"Access {self.icons[flag][1]}")

    @staticmethod
    def calculate_amplitude_envelope(audio, frame_length, hop_length):
        return np.array([max(audio[i:i + frame_length]) for i in range(0, len(audio), hop_length)])

    def switch_modes(self, visibility):
        self.ui.Grant_Access_To_Label.setVisible(visibility)
        for check_box in self.people_check_boxes:
            check_box.setVisible(visibility)
