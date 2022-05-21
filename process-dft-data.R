library(data.table)
library(stats19)

min_year <- 2000

process_dft_data <- function(input_file, type, min_year, output_file){
  data <- fread(input_file)
  
  data <- data[, accident_year:=as.integer(accident_year)]
  data <- data[accident_year >= min_year, ]
  
  formatted_data <- stats19:::format_stats19(data, type=type)
  
  fwrite(formatted_data, output_file)
}

process_dft_data("Downloads/dft-road-casualty-statistics-accident-1979-2020.csv", 'Accident', min_year, "Downloads/crashes.csv")
process_dft_data("Downloads/dft-road-casualty-statistics-casualty-1979-2020.csv", 'Casualty', min_year, "Downloads/casualties.csv")
process_dft_data("Downloads/dft-road-casualty-statistics-vehicle-1979-2020.csv", 'Vehicle', min_year, "Downloads/vehicles.csv")

