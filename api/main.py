from fastapi import FastAPI
import torch
import requests
from xml.etree import ElementTree as ET
import torch.nn as nn
import joblib
import numpy as np


def fetch_weather():
    url = "http://xmlweather.vedur.is/?op_w=xml&type=forec&lang=is&view=xml&ids=1;2&params=T;F"
    response = requests.get(url)

    # Check that the request was successful
    if response.status_code != 200:
        print(f"Request failed with status {response.status_code}")
        return

    # Parse the XML response
    tree = ET.fromstring(response.content)

    return tree


def get_temp_and_wind_speed():
    # Call the function to fetch weather data
    root = fetch_weather()

    # Extract the values between <T> and </T> tags
    t_values = [
        int(t.text) for t in root.findall(".//forecast/T") if t.text is not None
    ]
    f_values = [
        int(f.text) for f in root.findall(".//forecast/F") if f.text is not None
    ]  # Added for wind speed

    # Calculate the sum and count for temperature and wind speed
    t_sum = sum(t_values)
    t_count = len(t_values)

    f_sum = sum(f_values)  # Added for wind speed
    f_count = len(f_values)  # Added for wind speed

    # Calculate the average temperature and wind speed, and print the result
    average_temperature = t_sum / t_count if t_count > 0 else 0
    print(f"Average temperature: {average_temperature:.1f}°C")

    average_wind_speed = f_sum / f_count if f_count > 0 else 0  # Added for wind speed
    print(f"Average wind speed: {average_wind_speed:.1f} m/s")  # Added for wind speed

    return average_temperature, average_wind_speed


# Define the model architecture
class IslModel(nn.Module):
    def __init__(self):
        super(IslModel, self).__init__()
        self.linear = nn.Linear(1, 1)

    def forward(self, x):
        out = self.linear(x)
        return out


# Create an instance of the model
isl_model = IslModel()

# Load the state dictionary into the model
state_dict = torch.load("../models/isl-model.pt")
isl_model.load_state_dict(state_dict)


# Load the use model
usa_model = joblib.load("../models/usa-model.pt")

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/prediction/isl")
def predict_isl():
    current_average_temperature, current_average_wind_speed = get_temp_and_wind_speed()

    # standardize input
    x_mean = torch.tensor([4.3893])
    x_std = torch.tensor([4.1323])

    average_temperature = torch.tensor(
        current_average_temperature, dtype=torch.float32
    ).reshape(-1, 1)
    standardized_new_data = (average_temperature - x_mean) / x_std

    isl_model.eval()

    # Make a prediction based off of the current average temperature
    prediction = isl_model(standardized_new_data)
    prediction_value = prediction.item()

    # average accidents per month in Iceland is 246
    percentage_deviation = (prediction_value - 246) / 246 * 100
    return {
        "temp": current_average_temperature,
        "wind": current_average_wind_speed,
        "prediction": prediction_value,
        "percentage_deviation": percentage_deviation,
    }


@app.get("/prediction/usa")
def predict_isl():
    current_average_temperature, current_average_wind_speed = get_temp_and_wind_speed()

    # standardize input
    # Define the bins for temperature and wind speed
    temperature_bins = [-float("inf"), -5, 0, 5, 10, 15, 20, 25, 30, 35, float("inf")]
    wind_speed_bins = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, float("inf")]

    # Assign labels to each bin
    temperature_labels = [
        "Extremely Cold",
        "Very Cold",
        "Cold",
        "Slightly Cold",
        "Moderate Cold",
        "Moderate Hot",
        "Slightly Hot",
        "Hot",
        "Very Hot",
        "Extremely Hot",
    ]
    wind_speed_labels = [
        "No Wind",
        "Very Low",
        "Low",
        "Slightly Low",
        "Moderate Low",
        "Moderate High",
        "Slightly High",
        "High",
        "Very High",
        "Extremely High",
    ]

    current_temperature = 15
    current_wind_speed = 10

    # Encode the current temperature and wind speed values into one-hot encoding
    temperature_index = next(
        (i for i, bin in enumerate(temperature_bins) if current_temperature <= bin),
        len(temperature_bins) - 1,
    )
    wind_speed_index = next(
        (i for i, bin in enumerate(wind_speed_bins) if current_wind_speed <= bin)
    )

    # hacky way to solve out of index error
    if wind_speed_index == len(wind_speed_bins) - 1:
        wind_speed_index -= 1

    encoded_temperature = [0] * len(temperature_labels)
    encoded_temperature[temperature_index] = 1

    encoded_wind_speed = [0] * len(wind_speed_labels)
    encoded_wind_speed[wind_speed_index] = 1

    # Combine the encoded values into a single input tensor
    input_tensor = torch.tensor(
        [encoded_temperature + encoded_wind_speed], dtype=torch.float32
    )

    # Make the prediction using the trained model
    prediction = usa_model.predict(input_tensor)  # in log space
    prediction = np.exp(prediction) - 1e-5

    # Print the predicted amount of accidents
    print(f"Predicted amount of accidents: {prediction.item():.2f}")
    percentage_deviation = (prediction.item() - 20240.4) / 20240.4 * 100
    print(
        "percent deviation from average accidents per month: ",
        str(round(percentage_deviation, 3)) + "%",
    )

    return {
        "temp": current_average_temperature,
        "wind": current_average_wind_speed,
        "prediction": prediction.item(),
        "percent_deviation": percentage_deviation,
    }
