while true;do
	gpioset gpiochip0 23=1
	sleep 0.005
	gpioset gpiochip0 23=0
	sleep 0.005
done
